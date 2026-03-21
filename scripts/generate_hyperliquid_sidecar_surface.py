#!/usr/bin/env python3
"""Generate a real ETH 7d risk-surface artifact from local ABCI data."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from src.liquidationheatmap.hyperliquid.sidecar import (
    HyperliquidSidecarPrototypeBuilder,
    SidecarBuildRequest,
    SidecarPositionReconstructor,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="ETH", help="Target symbol, e.g. ETH or ETHUSDT")
    parser.add_argument("--timeframe-days", type=int, default=7, help="Analysis window in days")
    parser.add_argument(
        "--analysis-end",
        default="2026-03-21T00:00:00Z",
        help="Window end timestamp in ISO-8601 UTC.",
    )
    parser.add_argument("--output", type=Path, default=Path("data/validation/liqmap_hl_eth_7d.json"), help="Output path")
    return parser.parse_args()


def parse_analysis_end(raw: str) -> datetime:
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
    )
    
    print(f"Building plan for {request.symbol} {request.timeframe_days}d...")
    builder = HyperliquidSidecarPrototypeBuilder()
    plan = builder.build(request)
    
    print(f"Reconstructing state from {plan.anchor_coverage.latest_anchor_in_window}...")
    state = builder.reconstruct(request)
    
    print(f"Processing {len(state.users)} relevant accounts using Cross-Margin Solver...")
    
    reconstructor = SidecarPositionReconstructor()
    long_buckets: dict[float, float] = {}
    short_buckets: dict[float, float] = {}
    
    bin_size = plan.bin_size
    
    for user_state in state.users.values():
        target_pos = next((p for p in user_state.positions if p.coin == request.target_coin), None)
        if not target_pos or target_pos.size == 0:
            continue
            
        # Call the exact cross-margin solver
        liq_px = reconstructor.solve_liquidation_price(
            user_state=user_state,
            target_coin=request.target_coin,
            mark_prices=state.mark_prices,
            mmr_rates=state.mmr_rates
        )
        
        if liq_px is None or liq_px <= 0:
            # If no liquidation price or price is 0, they don't appear on the visible risk surface
            continue
            
        rounded_bin = math.floor(liq_px / bin_size) * bin_size
        # Volume is current notional: abs(size) * mark
        mark = state.mark_prices.get(target_pos.asset_idx, target_pos.entry_px)
        notional = abs(target_pos.size) * mark
        
        if target_pos.size > 0:
            buckets = long_buckets
        else:
            buckets = short_buckets
            
        buckets[rounded_bin] = buckets.get(rounded_bin, 0) + notional

    # Format result
    result = {
        "metadata": {
            "symbol": request.symbol,
            "target_coin": request.target_coin,
            "timestamp": state.timestamp.isoformat(),
            "bin_size": bin_size,
            "account_count": len(state.users),
            "source_anchor": str(plan.anchor_coverage.latest_anchor_in_window),
        },
        "long_liquidations": [
            {"price": p, "volume": v} for p, v in sorted(long_buckets.items())
        ],
        "short_liquidations": [
            {"price": p, "volume": v} for p, v in sorted(short_buckets.items())
        ],
    }
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(result, f, indent=2)
        
    print(f"Artifact generated at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
