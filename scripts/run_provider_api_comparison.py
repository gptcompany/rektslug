#!/usr/bin/env python3
"""Run the full provider capture and comparison workflow in one command."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.capture_provider_api import (
    BITCOINCOUNTERFLOW_DEFAULT_URL,
    DEFAULT_COINGLASS_URL,
    DEFAULT_OUTPUT_DIR as DEFAULT_CAPTURE_OUTPUT_DIR,
    run_capture,
)
from scripts.compare_provider_liquidations import generate_report

# spec-017 matrix: only these (symbol, timeframe) pairs are valid.
SPEC_017_SUPPORTED_SYMBOLS = {"BTC", "ETH"}
SPEC_017_SUPPORTED_TIMEFRAMES = {"1d", "1w"}
SPEC_017_SUPPORTED_PRODUCTS = {"liq-map"}
SPEC_017_ALLOWED_PROVIDERS = {"coinank", "coinglass", "rektslug", "both", "all"}


def validate_spec017_matrix(symbol: str, timeframe: str) -> None:
    """Fail fast if (symbol, timeframe) is outside the spec-017 matrix."""
    norm_symbol = symbol.strip().upper()
    norm_tf = timeframe.strip().lower()
    if norm_symbol not in SPEC_017_SUPPORTED_SYMBOLS:
        raise ValueError(
            f"Unsupported symbol: {symbol!r}. "
            f"Supported: {', '.join(sorted(SPEC_017_SUPPORTED_SYMBOLS))}"
        )
    if norm_tf not in SPEC_017_SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe: {timeframe!r}. "
            f"Supported: {', '.join(sorted(SPEC_017_SUPPORTED_TIMEFRAMES))}"
        )


def validate_product_filter(product: str | None) -> None:
    """Fail fast if the product is not liq-map."""
    if product is None:
        return  # defaults to liq-map
    if product not in SPEC_017_SUPPORTED_PRODUCTS:
        raise ValueError(
            f"Unsupported product: {product!r}. "
            f"Only liq-map is supported by spec-017."
        )


def validate_spec017_provider(provider: str) -> None:
    """Fail fast if a provider choice drifts outside the spec-017 scope."""
    if provider not in SPEC_017_ALLOWED_PROVIDERS:
        raise ValueError(
            f"Unsupported provider for spec-017: {provider!r}. "
            "Allowed: coinank, coinglass, rektslug, both, all."
        )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the combined workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=["coinank", "coinglass", "bitcoincounterflow", "rektslug", "both", "all"],
        default="all",
        help="Which provider(s) to capture before comparing.",
    )
    parser.add_argument("--coin", default="BTC", help="Base coin, e.g. BTC or ETH.")
    parser.add_argument(
        "--timeframe",
        default="1w",
        help="CoinAnk liq-map timeframe segment, e.g. 1d, 1w, 1M.",
    )
    parser.add_argument(
        "--exchange",
        default="binance",
        choices=["binance", "bybit", "hyperliquid"],
        help="Exchange for CoinAnk liq-map URL generation.",
    )
    parser.add_argument("--coinank-url", help="Override CoinAnk page URL.")
    parser.add_argument(
        "--coinglass-url",
        default=DEFAULT_COINGLASS_URL,
        help="Coinglass page URL to open. Defaults to the public LiquidationData page.",
    )
    parser.add_argument(
        "--bitcoincounterflow-url",
        default=BITCOINCOUNTERFLOW_DEFAULT_URL,
        help="Bitcoin CounterFlow page URL to open.",
    )
    parser.add_argument(
        "--capture-output-dir",
        type=Path,
        default=DEFAULT_CAPTURE_OUTPUT_DIR,
        help="Base directory for raw capture manifests.",
    )
    parser.add_argument(
        "--comparison-output",
        type=Path,
        help="Optional explicit output path for the normalized comparison report.",
    )
    parser.add_argument(
        "--max-responses",
        type=int,
        default=25,
        help="Maximum JSON responses to persist per provider.",
    )
    parser.add_argument(
        "--post-load-wait-ms",
        type=int,
        default=8000,
        help="How long to keep listening after page load/network idle.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Chromium with UI for debugging.",
    )
    parser.add_argument(
        "--no-persist-db",
        action="store_true",
        help="Skip persisting the normalized comparison report into DuckDB.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Override DuckDB path. Defaults to the validation DuckDB.",
    )
    parser.add_argument(
        "--product",
        default="liq-map",
        help="Product filter for comparison output. Only 'liq-map' is supported.",
    )
    parser.add_argument(
        "--matrix-preset",
        choices=["spec-017", "none"],
        default="none",
        help="Constrain coin/timeframe to a preset matrix. 'spec-017' = BTC/ETH x 1d/1w.",
    )
    parser.add_argument(
        "--coinglass-mode",
        choices=["browser", "rest", "auto"],
        default="rest",
        help="CoinGlass capture method. Default: 'rest'.",
    )
    parser.add_argument(
        "--profile",
        default="rektslug-default",
        help="Calibration profile for the local rektslug model (default: rektslug-default).",
    )
    parser.add_argument(
        "--include-rektslug",
        action="store_true",
        help="Also capture the local rektslug dataset alongside the selected provider(s).",
    )
    parser.add_argument(
        "--skip-gap-analysis",
        action="store_true",
        help="Skip the post-comparison gap-analysis step.",
    )
    return parser.parse_args()


def build_capture_namespace(args: argparse.Namespace) -> argparse.Namespace:
    """Translate combined CLI args into the capture script's expected namespace."""
    matrix_locked = args.matrix_preset == "spec-017"
    include_rektslug = matrix_locked and (
        args.provider in {"rektslug", "both", "all"} or getattr(args, "include_rektslug", False)
    )
    include_bitcoincounterflow = not matrix_locked

    return argparse.Namespace(
        provider=args.provider,
        coin=args.coin,
        timeframe=args.timeframe,
        exchange=args.exchange,
        coinank_url=args.coinank_url,
        coinglass_url=args.coinglass_url,
        bitcoincounterflow_url=getattr(args, "bitcoincounterflow_url", BITCOINCOUNTERFLOW_DEFAULT_URL),
        output_dir=args.capture_output_dir,
        max_responses=args.max_responses,
        post_load_wait_ms=args.post_load_wait_ms,
        headed=args.headed,
        coinglass_mode=getattr(args, "coinglass_mode", "rest"),
        coinglass_timeframe=None,
        include_rektslug=include_rektslug,
        include_bitcoincounterflow=include_bitcoincounterflow,
        profile=getattr(args, "profile", "rektslug-default"),
    )


def main() -> int:
    """CLI entry point."""
    args = parse_args()

    # Validate product filter (T005, T010)
    validate_product_filter(args.product)

    # Validate matrix preset (T006, T009, T011)
    if args.matrix_preset == "spec-017":
        validate_spec017_matrix(args.coin, args.timeframe)
        validate_spec017_provider(args.provider)

    capture_args = build_capture_namespace(args)

    manifest_path = asyncio.run(run_capture(capture_args, emit_progress=True))
    report, report_path = generate_report(
        manifest_paths=[manifest_path],
        output_path=args.comparison_output,
        persist_db=not args.no_persist_db,
        db_path=args.db_path,
        product_filter=args.product,
        profile=getattr(args, "profile", "rektslug-default"),
    )

    providers = sorted(report["providers"])
    print(f"normalized providers: {', '.join(providers)}")
    print(f"pairwise comparisons: {len(report['pairwise_comparisons'])}")
    if not args.no_persist_db:
        print("duckdb persistence: enabled")
    else:
        print("duckdb persistence: skipped")
    print(f"comparison report: {report_path}")

    if args.skip_gap_analysis:
        print("gap analysis: skipped")
        return 0

    # Run gap analysis on the same manifest (T027).
    gap_cmd = [
        sys.executable, str(REPO_ROOT / "scripts" / "provider_gap_analysis.py"),
        "--manifest", str(manifest_path),
    ]
    if not args.no_persist_db:
        gap_cmd.append("--persist-db")
    if args.db_path:
        gap_cmd.extend(["--db-path", str(args.db_path)])
    print("running gap analysis...")
    gap_result = subprocess.run(gap_cmd, capture_output=True, text=True)
    if gap_result.returncode == 0:
        gap_output = gap_result.stdout.strip()
        print(f"gap analysis: {gap_output}")
    else:
        gap_stderr = gap_result.stderr.strip()
        gap_stdout = gap_result.stdout.strip()
        if gap_stdout:
            print(f"gap analysis output: {gap_stdout}")
        print(f"gap analysis failed (exit {gap_result.returncode}): {gap_stderr}")
        return gap_result.returncode or 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
