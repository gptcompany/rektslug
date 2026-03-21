#!/usr/bin/env python3
"""Emit a bounded JSON plan for the first Hyperliquid sidecar prototype."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.liquidationheatmap.hyperliquid.sidecar import (
    HyperliquidSidecarPrototypeBuilder,
    SidecarBuildRequest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="ETH", help="Target symbol, e.g. ETH or ETHUSDT")
    parser.add_argument("--timeframe-days", type=int, default=7, help="Analysis window in days")
    parser.add_argument(
        "--analysis-end",
        default=None,
        help="Window end timestamp in ISO-8601 UTC. Defaults to current UTC time.",
    )
    parser.add_argument("--current-price", type=float, default=None, help="Optional current mark")
    parser.add_argument("--profile-name", default="rektslug-ank", help="Calibration profile name")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path")
    return parser.parse_args()


def parse_analysis_end(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> int:
    args = parse_args()
    request = SidecarBuildRequest(
        symbol=args.symbol,
        timeframe_days=args.timeframe_days,
        analysis_end=parse_analysis_end(args.analysis_end),
        current_price=args.current_price,
        profile_name=args.profile_name,
    )
    builder = HyperliquidSidecarPrototypeBuilder()
    payload = builder.build(request).to_dict()

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
