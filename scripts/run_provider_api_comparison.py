#!/usr/bin/env python3
"""Run the full provider capture and comparison workflow in one command."""

from __future__ import annotations

import argparse
import asyncio
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


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the combined workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=["coinank", "coinglass", "bitcoincounterflow", "both", "all"],
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
    return parser.parse_args()


def build_capture_namespace(args: argparse.Namespace) -> argparse.Namespace:
    """Translate combined CLI args into the capture script's expected namespace."""
    return argparse.Namespace(
        provider=args.provider,
        coin=args.coin,
        timeframe=args.timeframe,
        exchange=args.exchange,
        coinank_url=args.coinank_url,
        coinglass_url=args.coinglass_url,
        bitcoincounterflow_url=args.bitcoincounterflow_url,
        output_dir=args.capture_output_dir,
        max_responses=args.max_responses,
        post_load_wait_ms=args.post_load_wait_ms,
        headed=args.headed,
    )


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    capture_args = build_capture_namespace(args)

    manifest_path = asyncio.run(run_capture(capture_args, emit_progress=True))
    report, report_path = generate_report(
        manifest_paths=[manifest_path],
        output_path=args.comparison_output,
        persist_db=not args.no_persist_db,
        db_path=args.db_path,
    )

    providers = sorted(report["providers"])
    print(f"normalized providers: {', '.join(providers)}")
    print(f"pairwise comparisons: {len(report['pairwise_comparisons'])}")
    if not args.no_persist_db:
        print("duckdb persistence: enabled")
    else:
        print("duckdb persistence: skipped")
    print(f"comparison report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
