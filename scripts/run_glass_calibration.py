#!/usr/bin/env python3
"""Spec-019: Run rektslug-glass calibration against Coinglass.

By default this runner reuses the frozen Coinglass reference artifacts produced
by spec-017, then recalculates only the local rektslug side under the candidate
profile. This avoids bundle/auth drift during tuning while still benchmarking
against real provider captures.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_ank_calibration import (
    ACCEPT_ENTRIES_MIN,
    apply_acceptance_rule,
    aligned_bucket_overlap,
    check_critical_regression,
    compute_metrics_from_provider_metrics,
    evaluate_improvement,
    extract_bucket_prices_from_manifest,
    extract_provider_metrics,
    write_calibration_report,
)
from src.liquidationheatmap.models.profiles import get_profile

MATRIX = [
    ("BTC", "1d"),
    ("BTC", "1w"),
    ("ETH", "1d"),
    ("ETH", "1w"),
]

OUTPUT_DIR = REPO_ROOT / "data" / "validation" / "provider_comparisons"
GLASS_IMPROVEMENT_THRESHOLDS = {
    "bucket_count_proximity": 0.20,
    "long_short_total_ratio": 0.15,
    "long_short_peak_ratio": 0.15,
    "current_price_anchor": 0.10,
    # Coinglass liqMap clusters under top-level price buckets, so aligned-grid
    # overlap moves in smaller steps than the CoinAnK-oriented profile.
    "bucket_overlap": 0.05,
}


def normalize_report_timeframe(raw: str | None) -> str | None:
    mapping = {"1 day": "1d", "7 day": "1w"}
    if raw is None:
        return None
    return mapping.get(raw, raw)


def resolve_reference_reports() -> dict[tuple[str, str], tuple[dict, Path]]:
    """Pick the latest valid spec-017-style Coinglass reference report per matrix entry."""
    resolved: dict[tuple[str, str], tuple[dict, Path]] = {}
    for report_path in sorted(OUTPUT_DIR.glob("*_provider_liquidations.json")):
        try:
            report = json.loads(report_path.read_text())
        except Exception:
            continue

        coinglass = extract_provider_metrics(report, "coinglass")
        rektslug = extract_provider_metrics(report, "rektslug")
        if not coinglass or not rektslug:
            continue
        if coinglass.get("dataset_kind") != "liquidation_heatmap":
            continue
        if coinglass.get("structure") != "price_bins":
            continue
        if coinglass.get("bucket_count", 0) <= 0:
            continue

        key = (
            coinglass.get("symbol"),
            normalize_report_timeframe(coinglass.get("timeframe")),
        )
        if None in key:
            continue
        resolved[key] = (report, report_path)
    return resolved


def run_local_profile_capture(
    coin: str,
    timeframe: str,
    profile: str,
    attempts: int = 3,
) -> Path | None:
    """Run only the local rektslug side for a matrix entry."""
    import subprocess

    last_error = ""
    for attempt in range(1, attempts + 1):
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_provider_api_comparison.py"),
            "--provider",
            "rektslug",
            "--coin",
            coin,
            "--timeframe",
            timeframe,
            "--matrix-preset",
            "spec-017",
            "--profile",
            profile,
            "--no-persist-db",
            "--skip-gap-analysis",
        ]
        existing_reports = set(OUTPUT_DIR.glob("*_provider_liquidations.json"))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        candidate_paths: list[Path] = []
        for line in result.stdout.splitlines():
            if "comparison report:" not in line.lower():
                continue
            path_str = line.split(":", 1)[-1].strip()
            report_path = Path(path_str)
            if not report_path.is_absolute():
                report_path = REPO_ROOT / report_path
            if report_path.exists():
                candidate_paths.append(report_path)
        if not candidate_paths:
            current_reports = set(OUTPUT_DIR.glob("*_provider_liquidations.json"))
            candidate_paths = sorted(current_reports - existing_reports, reverse=True)

        for report_path in candidate_paths:
            try:
                report = json.loads(report_path.read_text())
            except Exception:
                continue
            if "rektslug" in report.get("providers", {}):
                return report_path

        last_error = result.stderr[:200]
        if attempt < attempts:
            print(f"    retrying local capture {coin} {timeframe} (attempt {attempt + 1}/{attempts})")
            time.sleep(2 * attempt)

    print(f"  local capture failed for {coin} {timeframe} profile={profile}: {last_error}")
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default="rektslug-glass",
        help="Calibration profile to evaluate (default: rektslug-glass).",
    )
    parser.add_argument(
        "--baseline-profile",
        default="rektslug-default",
        help="Baseline profile for comparison (default: rektslug-default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip actual capture runs, just show what would be done.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start_time = time.monotonic()

    print(f"spec-019 calibration: {args.baseline_profile} -> {args.profile}")
    print(f"matrix: {', '.join(f'{c} {tf}' for c, tf in MATRIX)}")

    if args.dry_run:
        print("dry-run: would load frozen Coinglass references and run local-only captures.")
        return 0

    try:
        cal_profile = get_profile(args.profile)
        get_profile(args.baseline_profile)
    except KeyError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"\n--- frozen provider references + baseline local captures ({args.baseline_profile}) ---")
    baseline_metrics = {}
    baseline_rektslug_reference = {}
    provider_reference = {}
    provider_bucket_prices = {}
    reference_reports = resolve_reference_reports()
    for coin, tf in MATRIX:
        print(f"  {coin} {tf}...")
        key = (f"{coin}USDT", tf)
        resolved = reference_reports.get(key)
        if not resolved:
            print("    WARNING: no valid frozen Coinglass reference found, skipping")
            continue

        report, report_path = resolved
        coinglass_metrics = extract_provider_metrics(report, "coinglass")
        if not coinglass_metrics:
            print("    WARNING: could not extract frozen Coinglass metrics")
            continue

        provider_reference[(coin, tf)] = coinglass_metrics
        manifest_path = Path(report["manifests"][0])
        ref_prices = extract_bucket_prices_from_manifest(manifest_path, "coinglass")
        provider_bucket_prices[(coin, tf)] = ref_prices

        local_report_path = run_local_profile_capture(
            coin,
            tf,
            args.baseline_profile,
        )
        if not local_report_path:
            print("    WARNING: baseline local capture failed, skipping")
            continue

        local_report = json.loads(local_report_path.read_text())
        rektslug_metrics = extract_provider_metrics(local_report, "rektslug")
        if not rektslug_metrics:
            print("    WARNING: could not extract baseline local rektslug metrics")
            continue

        baseline_rektslug_reference[(coin, tf)] = rektslug_metrics
        local_manifest_path = Path(local_report["manifests"][0])
        local_prices = extract_bucket_prices_from_manifest(local_manifest_path, "rektslug")
        baseline_metrics[(coin, tf)] = compute_metrics_from_provider_metrics(
            rektslug_metrics,
            coinglass_metrics,
        )
        baseline_metrics[(coin, tf)]["bucket_overlap"] = aligned_bucket_overlap(
            local_prices,
            ref_prices,
        )
        print(
            "    baseline metrics extracted from "
            f"{report_path.name} + {local_report_path.name}"
        )

    print(f"\n--- calibrated captures ({args.profile}) ---")
    calibrated_metrics = {}
    for coin, tf in MATRIX:
        print(f"  {coin} {tf}...")
        report_path = run_local_profile_capture(
            coin,
            tf,
            args.profile,
        )
        if not report_path:
            print("    WARNING: comparison failed, skipping")
            continue

        report = json.loads(report_path.read_text())
        rektslug_metrics = extract_provider_metrics(report, "rektslug")
        coinglass_metrics = provider_reference.get((coin, tf))
        baseline_rektslug_metrics = baseline_rektslug_reference.get((coin, tf))
        if not rektslug_metrics or not coinglass_metrics or not baseline_rektslug_metrics:
            print("    WARNING: could not extract rektslug_vs_coinglass metrics")
            continue

        frozen_rektslug_metrics = dict(rektslug_metrics)
        frozen_rektslug_metrics["current_price"] = baseline_rektslug_metrics["current_price"]
        calibrated_metrics[(coin, tf)] = compute_metrics_from_provider_metrics(
            frozen_rektslug_metrics,
            coinglass_metrics,
        )
        manifest_path = Path(report["manifests"][0])
        local_prices = extract_bucket_prices_from_manifest(manifest_path, "rektslug")
        calibrated_metrics[(coin, tf)]["bucket_overlap"] = aligned_bucket_overlap(
            local_prices,
            provider_bucket_prices.get((coin, tf), []),
        )
        print("    calibrated metrics extracted")

    print(f"\n--- acceptance evaluation ---")
    entry_results = []
    for coin, tf in MATRIX:
        key = (coin, tf)
        if key not in baseline_metrics or key not in calibrated_metrics:
            print(f"  {coin} {tf}: SKIP (missing data)")
            continue

        improvements = evaluate_improvement(
            baseline_metrics[key],
            calibrated_metrics[key],
            thresholds=GLASS_IMPROVEMENT_THRESHOLDS,
        )
        regression = check_critical_regression(baseline_metrics[key], calibrated_metrics[key])
        passed_count = sum(1 for v in improvements.values() if v["passed"])
        print(
            f"  {coin} {tf}: {passed_count}/5 metrics improved"
            + (f" CRITICAL REGRESSION: {regression}" if regression else "")
        )
        entry_results.append(
            {
                "symbol": coin,
                "timeframe": tf,
                "improvements": improvements,
                "critical_regression": regression,
                "baseline": baseline_metrics[key],
                "calibrated": calibrated_metrics[key],
            }
        )

    acceptance = apply_acceptance_rule(entry_results)
    elapsed = time.monotonic() - start_time

    final_report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "baseline_profile": args.baseline_profile,
        "profile_params": cal_profile.to_dict(),
        "improvement_thresholds": GLASS_IMPROVEMENT_THRESHOLDS,
        "status": "accepted" if acceptance["accepted"] else "rejected",
        "acceptance": acceptance,
        "entry_results": entry_results,
        "elapsed_seconds": round(elapsed, 1),
        "matrix": [{"symbol": c, "timeframe": tf} for c, tf in MATRIX],
    }

    report_path = write_calibration_report(final_report, args.profile)
    print(f"\n--- result ---")
    print(f"status: {final_report['status']}")
    print(f"entries passing: {acceptance['entries_passing']}/{len(MATRIX)} (need {ACCEPT_ENTRIES_MIN})")
    print(f"critical regression: {'YES' if acceptance['has_critical_regression'] else 'no'}")
    print(f"elapsed: {elapsed:.1f}s")
    print(f"report: {report_path}")
    print(f"report size: {report_path.stat().st_size} bytes")

    return 0 if acceptance["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
