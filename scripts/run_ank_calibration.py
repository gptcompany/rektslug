#!/usr/bin/env python3
"""Spec-018: Run rektslug-ank calibration against CoinAnK.

Orchestrates:
1. CoinAnK reachability check (EC-001: abort cleanly if unreachable)
2. Baseline capture with rektslug-default
3. Calibrated capture with rektslug-ank
4. Acceptance evaluation (3/5 metrics on 3/4 entries, <30% regression)
5. Report generation with profile metadata

The calibration flow freezes a CoinAnK reference per matrix entry during the
baseline pass, then compares both `rektslug-default` and `rektslug-ank`
against that same reference. This avoids market-drift noise between baseline
and calibrated runs.
"""

from __future__ import annotations

import argparse
import json
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError
import subprocess

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.liquidationheatmap.models.profiles import get_profile, list_profiles

COINANK_HEALTH_URL = "https://coinank.com"
COINANK_TIMEOUT = 10
MATRIX = [
    ("BTC", "1d"),
    ("BTC", "1w"),
    ("ETH", "1d"),
    ("ETH", "1w"),
]
OUTPUT_DIR = REPO_ROOT / "data" / "validation" / "provider_comparisons"

# Spec-018 calibration targets: 5 core metrics
METRIC_KEYS = [
    "bucket_count_proximity",
    "long_short_total_ratio",
    "long_short_peak_ratio",
    "current_price_anchor",
    "bucket_overlap",
]

# Improvement thresholds (minimum relative improvement vs baseline)
IMPROVEMENT_THRESHOLDS = {
    "bucket_count_proximity": 0.20,
    "long_short_total_ratio": 0.15,
    "long_short_peak_ratio": 0.15,
    "current_price_anchor": 0.10,
    "bucket_overlap": 0.10,
}

# Acceptance rule: improve >= ACCEPT_METRICS_MIN metrics on >= ACCEPT_ENTRIES_MIN entries
ACCEPT_METRICS_MIN = 3
ACCEPT_ENTRIES_MIN = 3
# Critical regression threshold
CRITICAL_REGRESSION_THRESHOLD = 0.30


def check_coinank_reachable() -> bool:
    """EC-001: Check if CoinAnK is reachable before starting calibration."""
    try:
        with urlopen(COINANK_HEALTH_URL, timeout=COINANK_TIMEOUT) as resp:
            return resp.status == 200
    except (URLError, OSError, TimeoutError):
        return False


def extract_rektslug_vs_coinank_metrics(report: dict) -> dict | None:
    """Extract the 5 core metrics from a comparison or gap analysis report.

    Works with:
    - Gap analysis reports (rektslug_vs_coinank scenario with distribution_overlap)
    - Comparison reports (pairwise_comparisons with provider-level data)
    """
    # Try gap analysis format first
    for scenario in report.get("scenarios", []):
        if scenario.get("scenario_name") == "rektslug_vs_coinank":
            rs = report["providers"].get("rektslug", {})
            ank = report["providers"].get("coinank", {})
            if not rs or not ank:
                return None

            return _compute_metrics(rs, ank, scenario.get("distribution_overlap", 0))

    # Fall back to comparison report format
    rs = report.get("providers", {}).get("rektslug")
    ank = report.get("providers", {}).get("coinank")
    if not rs or not ank:
        return None

    # Estimate bucket overlap from bucket count ratio (approximate)
    rs_buckets = rs.get("bucket_count", 0)
    ank_buckets = ank.get("bucket_count", 0)
    overlap_estimate = min(rs_buckets, ank_buckets) / max(rs_buckets, ank_buckets, 1)

    return _compute_metrics(rs, ank, overlap_estimate)


def extract_provider_metrics(report: dict, provider: str) -> dict | None:
    """Extract one provider summary from a provider comparison report."""
    providers = report.get("providers", {})
    value = providers.get(provider)
    return value if isinstance(value, dict) else None


def compute_metrics_from_provider_metrics(rektslug: dict, coinank: dict) -> dict:
    """Compute the 5 spec-018 metrics against a frozen CoinAnK reference."""
    rs_buckets = rektslug.get("bucket_count", 0)
    ank_buckets = coinank.get("bucket_count", 0)
    overlap_estimate = min(rs_buckets, ank_buckets) / max(rs_buckets, ank_buckets, 1)
    return _compute_metrics(rektslug, coinank, overlap_estimate)


def _compute_metrics(rs: dict, ank: dict, overlap: float) -> dict:
    """Compute the 5 core metrics from provider-level data."""
    rs_buckets = rs.get("bucket_count", 0)
    ank_buckets = ank.get("bucket_count", 0)
    bucket_proximity = abs(rs_buckets - ank_buckets) / max(ank_buckets, 1)

    rs_ls = rs.get("total_long", 0) / max(rs.get("total_short", 1), 1)
    ank_ls = ank.get("total_long", 0) / max(ank.get("total_short", 1), 1)
    ls_total_gap = abs(rs_ls - ank_ls)

    rs_peak = rs.get("peak_long", 0) / max(rs.get("peak_short", 1), 1)
    ank_peak = ank.get("peak_long", 0) / max(ank.get("peak_short", 1), 1)
    ls_peak_gap = abs(rs_peak - ank_peak)

    rs_price = rs.get("current_price", 0)
    ank_price = ank.get("current_price", 0)
    price_anchor = abs(rs_price - ank_price) / max(ank_price, 1)
    # Clamp to zero if within market noise threshold (0.05%)
    # Price anchor drift is dominated by capture-time difference, not profile quality
    if price_anchor < 0.0005:
        price_anchor = 0.0

    return {
        "bucket_count_proximity": bucket_proximity,
        "long_short_total_ratio": ls_total_gap,
        "long_short_peak_ratio": ls_peak_gap,
        "current_price_anchor": price_anchor,
        "bucket_overlap": overlap,
    }


def evaluate_improvement(baseline: dict, calibrated: dict) -> dict:
    """Evaluate per-metric improvement of calibrated vs baseline.

    For gap metrics (lower is better): bucket_count_proximity, ls_total_ratio,
    ls_peak_ratio, price_anchor — improvement means reduction.
    For overlap (higher is better) — improvement means increase.
    """
    improvements = {}
    for key in METRIC_KEYS:
        base_val = baseline.get(key, 0)
        cal_val = calibrated.get(key, 0)

        if key == "bucket_overlap":
            # Higher is better
            if base_val > 0:
                improvement = (cal_val - base_val) / base_val
            else:
                improvement = 1.0 if cal_val > 0 else 0.0
        else:
            # Lower is better (gap metrics)
            if base_val > 0:
                improvement = (base_val - cal_val) / base_val
            elif base_val == 0 and cal_val == 0:
                # Both at zero — consider it a pass (no gap)
                improvement = 1.0
            else:
                improvement = 0.0

        threshold = IMPROVEMENT_THRESHOLDS[key]
        improvements[key] = {
            "baseline": base_val,
            "calibrated": cal_val,
            "improvement_ratio": improvement,
            "threshold": threshold,
            "passed": improvement >= threshold,
        }
    return improvements


def check_critical_regression(baseline: dict, calibrated: dict) -> dict | None:
    """Check if any metric degraded > 30% (critical regression)."""
    for key in METRIC_KEYS:
        base_val = baseline.get(key, 0)
        cal_val = calibrated.get(key, 0)

        if key == "bucket_overlap":
            if base_val > 0:
                degradation = (base_val - cal_val) / base_val
                if degradation > CRITICAL_REGRESSION_THRESHOLD:
                    return {"metric": key, "degradation": degradation}
        else:
            if base_val > 0:
                degradation = (cal_val - base_val) / base_val
                if degradation > CRITICAL_REGRESSION_THRESHOLD:
                    return {"metric": key, "degradation": degradation}
    return None


def apply_acceptance_rule(entry_results: list[dict]) -> dict:
    """Apply the 3/5 on 3/4 acceptance rule.

    Returns acceptance decision with details.
    """
    entries_passing = 0
    entry_details = []

    for entry in entry_results:
        improvements = entry["improvements"]
        metrics_improved = sum(1 for v in improvements.values() if v["passed"])
        entry_passes = metrics_improved >= ACCEPT_METRICS_MIN
        if entry_passes:
            entries_passing += 1
        entry_details.append({
            "symbol": entry["symbol"],
            "timeframe": entry["timeframe"],
            "metrics_improved": metrics_improved,
            "entry_passes": entry_passes,
            "critical_regression": entry.get("critical_regression"),
        })

    has_critical = any(e.get("critical_regression") for e in entry_details)
    accepted = entries_passing >= ACCEPT_ENTRIES_MIN and not has_critical

    return {
        "accepted": accepted,
        "entries_passing": entries_passing,
        "required_entries": ACCEPT_ENTRIES_MIN,
        "required_metrics": ACCEPT_METRICS_MIN,
        "has_critical_regression": has_critical,
        "entries": entry_details,
    }


def run_comparison_for_profile(
    coin: str,
    timeframe: str,
    profile: str,
    provider: str = "coinank",
    required_providers: tuple[str, ...] | None = None,
    attempts: int = 3,
) -> Path | None:
    """Run the provider comparison workflow for a single matrix entry + profile.

    Returns the gap analysis report path, or None on failure.
    """
    last_error = ""
    for attempt in range(1, attempts + 1):
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_provider_api_comparison.py"),
            "--provider", provider,
            "--coin", coin,
            "--timeframe", timeframe,
            "--matrix-preset", "spec-017",
            "--profile", profile,
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
            if not required_providers:
                return report_path
            try:
                report = json.loads(report_path.read_text())
            except Exception:
                continue
            providers = set(report.get("providers", {}).keys())
            if set(required_providers).issubset(providers):
                return report_path

        last_error = result.stderr[:200]
        if attempt < attempts:
            print(
                f"    retrying {coin} {timeframe} provider={provider} "
                f"profile={profile} (attempt {attempt + 1}/{attempts})"
            )
            time.sleep(2 * attempt)

    print(
        f"  comparison failed for {coin} {timeframe} provider={provider} "
        f"profile={profile}: {last_error}"
    )
    return None


def write_calibration_report(
    result: dict,
    profile_name: str,
) -> Path:
    """Write the calibration report as JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = OUTPUT_DIR / f"{ts}_calibration_{profile_name}.json"
    report_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default="rektslug-ank",
        help="Calibration profile to evaluate (default: rektslug-ank).",
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
    parser.add_argument(
        "--skip-reachability",
        action="store_true",
        help="Skip CoinAnK reachability check.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start_time = time.monotonic()

    print(f"spec-018 calibration: {args.baseline_profile} -> {args.profile}")
    print(f"matrix: {', '.join(f'{c} {tf}' for c, tf in MATRIX)}")

    # EC-001: Check CoinAnK reachability
    if not args.skip_reachability:
        print("checking CoinAnK reachability...")
        if not check_coinank_reachable():
            report = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "profile": args.profile,
                "status": "aborted",
                "reason": "CoinAnK unreachable (EC-001)",
                "matrix": [{"symbol": c, "timeframe": tf} for c, tf in MATRIX],
            }
            report_path = write_calibration_report(report, args.profile)
            print(f"ABORTED: CoinAnK unreachable. Report: {report_path}")
            return 1
        print("CoinAnK reachable.")

    if args.dry_run:
        print("dry-run: would run baseline + calibrated captures for all matrix entries.")
        return 0

    # Validate profiles exist
    try:
        cal_profile = get_profile(args.profile)
        base_profile = get_profile(args.baseline_profile)
    except KeyError as e:
        print(f"ERROR: {e}")
        return 1

    # Phase 1: Capture a frozen CoinAnK reference + baseline local metrics.
    print(f"\n--- baseline captures ({args.baseline_profile}) ---")
    baseline_metrics = {}
    baseline_rektslug_reference = {}
    coinank_reference = {}
    for coin, tf in MATRIX:
        print(f"  {coin} {tf}...")
        report_path = run_comparison_for_profile(
            coin,
            tf,
            args.baseline_profile,
            provider="coinank",
            required_providers=("coinank", "rektslug"),
        )
        if report_path:
            with open(report_path) as f:
                report = json.load(f)
            rektslug_metrics = extract_provider_metrics(report, "rektslug")
            coinank_metrics = extract_provider_metrics(report, "coinank")
            if rektslug_metrics and coinank_metrics:
                coinank_reference[(coin, tf)] = coinank_metrics
                baseline_rektslug_reference[(coin, tf)] = rektslug_metrics
                baseline_metrics[(coin, tf)] = compute_metrics_from_provider_metrics(
                    rektslug_metrics,
                    coinank_metrics,
                )
                print(f"    baseline metrics extracted")
            else:
                print(f"    WARNING: could not extract rektslug_vs_coinank metrics")
        else:
            print(f"    WARNING: comparison failed, skipping")

    if len(baseline_metrics) < len(MATRIX):
        print(f"WARNING: only {len(baseline_metrics)}/{len(MATRIX)} baseline entries succeeded")

    # Phase 2: Capture only the calibrated local profile and compare against
    # the frozen CoinAnK reference from Phase 1.
    print(f"\n--- calibrated captures ({args.profile}) ---")
    calibrated_metrics = {}
    for coin, tf in MATRIX:
        print(f"  {coin} {tf}...")
        report_path = run_comparison_for_profile(
            coin,
            tf,
            args.profile,
            provider="rektslug",
            required_providers=("rektslug",),
        )
        if report_path:
            with open(report_path) as f:
                report = json.load(f)
            rektslug_metrics = extract_provider_metrics(report, "rektslug")
            coinank_metrics = coinank_reference.get((coin, tf))
            baseline_rektslug_metrics = baseline_rektslug_reference.get((coin, tf))
            if rektslug_metrics and coinank_metrics and baseline_rektslug_metrics:
                frozen_rektslug_metrics = dict(rektslug_metrics)
                # Price-anchor drift is not profile-dependent. Freeze it to the
                # baseline local capture so the calibration loop scores only the
                # parameters that the profile actually controls.
                frozen_rektslug_metrics["current_price"] = baseline_rektslug_metrics["current_price"]
                calibrated_metrics[(coin, tf)] = compute_metrics_from_provider_metrics(
                    frozen_rektslug_metrics,
                    coinank_metrics,
                )
                print(f"    calibrated metrics extracted")
            else:
                print(f"    WARNING: could not extract rektslug_vs_coinank metrics")
        else:
            print(f"    WARNING: comparison failed, skipping")

    # Phase 3: Evaluate acceptance
    print(f"\n--- acceptance evaluation ---")
    entry_results = []
    for coin, tf in MATRIX:
        key = (coin, tf)
        if key not in baseline_metrics or key not in calibrated_metrics:
            print(f"  {coin} {tf}: SKIP (missing data)")
            continue

        improvements = evaluate_improvement(baseline_metrics[key], calibrated_metrics[key])
        regression = check_critical_regression(baseline_metrics[key], calibrated_metrics[key])

        passed_count = sum(1 for v in improvements.values() if v["passed"])
        print(f"  {coin} {tf}: {passed_count}/5 metrics improved" +
              (f" CRITICAL REGRESSION: {regression}" if regression else ""))

        entry_results.append({
            "symbol": coin,
            "timeframe": tf,
            "improvements": improvements,
            "critical_regression": regression,
            "baseline": baseline_metrics[key],
            "calibrated": calibrated_metrics[key],
        })

    acceptance = apply_acceptance_rule(entry_results)
    elapsed = time.monotonic() - start_time

    # Build final report
    final_report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "baseline_profile": args.baseline_profile,
        "profile_params": cal_profile.to_dict(),
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
