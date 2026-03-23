#!/usr/bin/env python3
"""Quantify snapshot position margin vs current solver maintenance margin."""

from __future__ import annotations

import argparse
import json
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
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/validation/hl_open_order_margin_gap_eth_7d.json"),
        help="Output path",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="How many largest-gap positions/users to retain in the report.",
    )
    return parser.parse_args()


def parse_analysis_end(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def quantile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    idx = int(round((len(sorted_values) - 1) * p))
    return float(sorted_values[idx])


def summarize(records: list[dict], *, snapshot_key: str, solver_key: str, gap_key: str) -> dict:
    snapshot_values = [float(record[snapshot_key]) for record in records]
    solver_values = [float(record[solver_key]) for record in records]
    gaps = [float(record[gap_key]) for record in records]

    positive = [gap for gap in gaps if gap > 0]
    negative = [gap for gap in gaps if gap < 0]

    return {
        "count": len(records),
        "snapshot_total": round(sum(snapshot_values), 6),
        "solver_total": round(sum(solver_values), 6),
        "gap_total": round(sum(gaps), 6),
        "positive_gap_count": len(positive),
        "negative_gap_count": len(negative),
        "zero_gap_count": len(records) - len(positive) - len(negative),
        "positive_gap_total": round(sum(positive), 6),
        "negative_gap_total": round(sum(negative), 6),
        "gap_mean": round(sum(gaps) / len(gaps), 6) if gaps else None,
        "gap_median": round(quantile(gaps, 0.5), 6) if gaps else None,
        "gap_p90": round(quantile(gaps, 0.9), 6) if gaps else None,
        "gap_p95": round(quantile(gaps, 0.95), 6) if gaps else None,
        "gap_p99": round(quantile(gaps, 0.99), 6) if gaps else None,
        "gap_min": round(min(gaps), 6) if gaps else None,
        "gap_max": round(max(gaps), 6) if gaps else None,
    }


def main() -> int:
    args = parse_args()
    request = SidecarBuildRequest(
        symbol=args.symbol,
        timeframe_days=args.timeframe_days,
        analysis_end=parse_analysis_end(args.analysis_end),
    )

    builder = HyperliquidSidecarPrototypeBuilder()
    plan = builder.build(request)
    state = builder.reconstruct(request)
    reconstructor = SidecarPositionReconstructor()

    all_positions: list[dict] = []
    target_positions: list[dict] = []
    users: list[dict] = []
    coin_breakdown: dict[str, dict[str, float | int]] = {}

    for user_state in state.users.values():
        user_snapshot_total = 0.0
        user_solver_total = 0.0
        user_target_snapshot_total = 0.0
        user_target_solver_total = 0.0
        user_target_position_count = 0

        for position in user_state.positions:
            solver_margin = reconstructor.compute_position_maintenance_margin(
                position,
                state.mark_prices,
                state.asset_margin_tiers,
            )
            mark = state.mark_prices.get(position.asset_idx, position.entry_px)
            notional = abs(position.size) * mark
            gap = position.margin - solver_margin
            row = {
                "user": user_state.user,
                "coin": position.coin,
                "size": round(position.size, 10),
                "entry_px": round(position.entry_px, 10),
                "mark_px": round(mark, 10),
                "notional": round(notional, 6),
                "snapshot_margin": round(position.margin, 6),
                "solver_mmr": round(solver_margin, 6),
                "margin_gap": round(gap, 6),
                "gap_ratio_vs_mmr": round(gap / solver_margin, 6) if solver_margin > 0 else None,
            }
            all_positions.append(row)
            user_snapshot_total += position.margin
            user_solver_total += solver_margin

            coin_stats = coin_breakdown.setdefault(
                position.coin,
                {
                    "position_count": 0,
                    "snapshot_total": 0.0,
                    "solver_total": 0.0,
                    "gap_total": 0.0,
                },
            )
            coin_stats["position_count"] += 1
            coin_stats["snapshot_total"] += position.margin
            coin_stats["solver_total"] += solver_margin
            coin_stats["gap_total"] += gap

            if position.coin == request.target_coin:
                target_positions.append(row)
                user_target_position_count += 1
                user_target_snapshot_total += position.margin
                user_target_solver_total += solver_margin

        users.append(
            {
                "user": user_state.user,
                "position_count": len(user_state.positions),
                "target_position_count": user_target_position_count,
                "snapshot_margin_total": round(user_snapshot_total, 6),
                "solver_mmr_total": round(user_solver_total, 6),
                "margin_gap_total": round(user_snapshot_total - user_solver_total, 6),
                "target_snapshot_margin_total": round(user_target_snapshot_total, 6),
                "target_solver_mmr_total": round(user_target_solver_total, 6),
                "target_margin_gap_total": round(user_target_snapshot_total - user_target_solver_total, 6),
            }
        )

    coin_breakdown_out = {
        coin: {
            "position_count": stats["position_count"],
            "snapshot_total": round(float(stats["snapshot_total"]), 6),
            "solver_total": round(float(stats["solver_total"]), 6),
            "gap_total": round(float(stats["gap_total"]), 6),
        }
        for coin, stats in sorted(coin_breakdown.items())
    }

    result = {
        "metadata": {
            "symbol": request.symbol,
            "target_coin": request.target_coin,
            "timeframe_days": request.timeframe_days,
            "analysis_end_utc": request.analysis_end.isoformat(),
            "source_anchor": str(plan.anchor_coverage.latest_anchor_in_window),
            "account_count": len(state.users),
            "all_position_count": len(all_positions),
            "target_position_count": len(target_positions),
        },
        "interpretation": {
            "gap_definition": "snapshot_margin - solver_mmr",
            "positive_gap_meaning": "Snapshot margin exceeds current maintenance margin; this is consistent with reserved-margin or discretionary excess collateral but is not proof of open-order usage on its own.",
            "negative_gap_meaning": "Snapshot margin is below current maintenance margin; this indicates the M field is not a direct maintenance-margin proxy at current marks and should not be interpreted as reserved-margin evidence.",
        },
        "all_positions_summary": summarize(
            all_positions,
            snapshot_key="snapshot_margin",
            solver_key="solver_mmr",
            gap_key="margin_gap",
        ),
        "target_positions_summary": summarize(
            target_positions,
            snapshot_key="snapshot_margin",
            solver_key="solver_mmr",
            gap_key="margin_gap",
        ),
        "user_summary": summarize(
            users,
            snapshot_key="snapshot_margin_total",
            solver_key="solver_mmr_total",
            gap_key="margin_gap_total",
        ),
        "coin_breakdown": coin_breakdown_out,
        "top_target_positions_by_abs_gap": sorted(
            target_positions,
            key=lambda row: abs(float(row["margin_gap"])),
            reverse=True,
        )[: args.top_n],
        "top_users_by_abs_gap": sorted(
            users,
            key=lambda row: abs(float(row["margin_gap_total"])),
            reverse=True,
        )[: args.top_n],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Margin-gap report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
