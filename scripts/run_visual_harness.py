#!/usr/bin/env python3
"""Run the visual comparison harness for a single comparison pair."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.liquidationheatmap.validation.visual_harness.runner import (
    VisualHarnessRequest,
    run_visual_pair,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Stable run identifier. Defaults to UTC timestamp-based id.")
    parser.add_argument("--product", choices=["liq-map", "liq-heat-map"], default="liq-map")
    parser.add_argument("--renderer", choices=["plotly", "lightweight"], default="plotly")
    parser.add_argument("--provider", default="coinank")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--api-base", default="http://localhost:8002")
    parser.add_argument(
        "--pass-threshold",
        type=int,
        default=95,
        help="Visual similarity threshold (90-100, default: 95).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/validation/visual_harness"),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--timeframe", choices=["1d", "1w"])
    group.add_argument("--window")
    args = parser.parse_args()
    if args.pass_threshold < 90 or args.pass_threshold > 100:
        parser.error("--pass-threshold must be between 90 and 100")
    return args


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("visual_%Y%m%dT%H%M%SZ")


def main() -> int:
    args = parse_args()
    request = VisualHarnessRequest(
        run_id=args.run_id or _default_run_id(),
        product=args.product,
        renderer=args.renderer,
        provider=args.provider,
        symbol=args.symbol,
        exchange=args.exchange,
        timeframe=args.timeframe,
        window=args.window,
        api_base=args.api_base,
    )
    outcome = run_visual_pair(
        request=request,
        output_dir=args.output_dir,
        pass_threshold=args.pass_threshold,
    )
    print(f"manifest={outcome.manifest_path}")
    if outcome.score_path is not None:
        print(f"score={outcome.score_path}")
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
