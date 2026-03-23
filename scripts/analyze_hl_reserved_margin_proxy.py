#!/usr/bin/env python3
"""Analyze bounded reserved-margin proxies from reconstructed resting orders."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.liquidationheatmap.hyperliquid.sidecar import (
    HyperliquidSidecarPrototypeBuilder,
    SidecarBuildRequest,
    SidecarPositionReconstructor,
    iter_zst_jsonl,
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
        "--order-status-file",
        type=Path,
        required=True,
        help="Path to a node_order_statuses_by_block hourly .zst file.",
    )
    parser.add_argument(
        "--raw-book-diff-file",
        type=Path,
        required=True,
        help="Path to a node_raw_book_diffs_by_block hourly .zst file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/validation/hl_reserved_margin_proxy_eth_sample.json"),
        help="Output path.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="How many top rows to keep in the output.",
    )
    return parser.parse_args()


def parse_analysis_end(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): to_jsonable(val) for key, val in value.items()}
    if hasattr(value, "items") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return {str(key): to_jsonable(val) for key, val in value.items()}
        except TypeError:
            pass
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


def main() -> int:
    args = parse_args()
    request = SidecarBuildRequest(
        symbol=args.symbol,
        timeframe_days=args.timeframe_days,
        analysis_end=parse_analysis_end(args.analysis_end),
    )

    builder = HyperliquidSidecarPrototypeBuilder()
    plan = builder.build(request)
    if not plan.anchor_coverage.latest_anchor_in_window:
        raise ValueError(f"No anchors available in window for {request.symbol}")

    reconstructor = SidecarPositionReconstructor()
    active_user_ids = reconstructor.collect_active_order_users_from_blocks(
        order_status_blocks=iter_zst_jsonl(args.order_status_file),
        raw_book_diff_blocks=iter_zst_jsonl(args.raw_book_diff_file),
    )
    sidecar_state = reconstructor.load_abci_anchor(
        plan.anchor_coverage.latest_anchor_in_window,
        target_coin=request.target_coin,
        target_users=active_user_ids,
    )
    orders_by_user = reconstructor.reconstruct_resting_orders_from_blocks(
        order_status_blocks=iter_zst_jsonl(args.order_status_file),
        raw_book_diff_blocks=iter_zst_jsonl(args.raw_book_diff_file),
        target_users=set(sidecar_state.users),
    )

    rows: list[dict] = []
    total_active_notional = 0.0
    total_non_reduce_only_notional = 0.0
    total_lower_bound = 0.0
    total_upper_bound = 0.0
    total_target_lower_bound = 0.0
    total_target_upper_bound = 0.0
    total_off_target_lower_bound = 0.0
    total_off_target_upper_bound = 0.0
    users_with_off_target_bounds = 0
    users_with_negative_gap = 0
    users_with_positive_gap = 0

    for user, orders in orders_by_user.items():
        user_state = sidecar_state.users.get(user)
        if user_state is None:
            continue

        snapshot_margin_total = 0.0
        solver_mmr_total = 0.0
        for position in user_state.positions:
            snapshot_margin_total += position.margin
            solver_mmr_total += reconstructor.compute_position_maintenance_margin(
                position,
                sidecar_state.mark_prices,
                sidecar_state.asset_margin_tiers,
            )
        margin_gap_total = snapshot_margin_total - solver_mmr_total
        if margin_gap_total < 0:
            users_with_negative_gap += 1
        elif margin_gap_total > 0:
            users_with_positive_gap += 1

        bounds = reconstructor.compute_resting_order_exposure_bounds(
            user_state,
            orders,
            target_coin=request.target_coin,
        )
        if bounds.off_target_exposure_increasing_upper_bound > 0:
            users_with_off_target_bounds += 1

        total_active_notional += bounds.total_active_notional
        total_non_reduce_only_notional += bounds.non_reduce_only_notional
        total_lower_bound += bounds.exposure_increasing_notional_lower_bound
        total_upper_bound += bounds.exposure_increasing_notional_upper_bound
        total_target_lower_bound += bounds.target_coin_exposure_increasing_lower_bound
        total_target_upper_bound += bounds.target_coin_exposure_increasing_upper_bound
        total_off_target_lower_bound += bounds.off_target_exposure_increasing_lower_bound
        total_off_target_upper_bound += bounds.off_target_exposure_increasing_upper_bound

        rows.append(
            {
                "user": user,
                "position_count": len(user_state.positions),
                "active_order_count": bounds.active_order_count,
                "non_reduce_only_order_count": bounds.non_reduce_only_order_count,
                "reduce_only_order_count": bounds.reduce_only_order_count,
                "snapshot_margin_total": round(snapshot_margin_total, 6),
                "solver_mmr_total": round(solver_mmr_total, 6),
                "margin_gap_total": round(margin_gap_total, 6),
                "total_active_notional": bounds.total_active_notional,
                "non_reduce_only_notional": bounds.non_reduce_only_notional,
                "reduce_only_notional": bounds.reduce_only_notional,
                "exposure_increasing_notional_lower_bound": bounds.exposure_increasing_notional_lower_bound,
                "exposure_increasing_notional_upper_bound": bounds.exposure_increasing_notional_upper_bound,
                "target_coin_exposure_increasing_lower_bound": bounds.target_coin_exposure_increasing_lower_bound,
                "target_coin_exposure_increasing_upper_bound": bounds.target_coin_exposure_increasing_upper_bound,
                "off_target_exposure_increasing_lower_bound": bounds.off_target_exposure_increasing_lower_bound,
                "off_target_exposure_increasing_upper_bound": bounds.off_target_exposure_increasing_upper_bound,
                "per_coin": to_jsonable(bounds.per_coin),
            }
        )

    result = {
        "metadata": {
            "symbol": request.symbol,
            "target_coin": request.target_coin,
            "timeframe_days": request.timeframe_days,
            "analysis_end_utc": request.analysis_end.isoformat(),
            "source_anchor": str(plan.anchor_coverage.latest_anchor_in_window),
            "order_status_file": str(args.order_status_file),
            "raw_book_diff_file": str(args.raw_book_diff_file),
            "feed_active_user_candidate_count": len(active_user_ids),
            "target_user_count": len(sidecar_state.users),
            "active_user_count": len(rows),
            "order_status_block_count": None,
            "raw_book_diff_block_count": None,
        },
        "interpretation": {
            "bounded_proxy_definition": "Exposure-increasing lower/upper bounds are measured in order notional, not exact reserved margin.",
            "lower_bound_meaning": "Notional that definitely increases exposure after excluding reduce-only orders and netting opposite-side orders against the current position size.",
            "upper_bound_meaning": "Notional that could increase exposure within the retained block sample when opposite-side orders collectively exceed the current position size.",
        },
        "summary": {
            "total_active_notional": round(total_active_notional, 6),
            "total_non_reduce_only_notional": round(total_non_reduce_only_notional, 6),
            "total_exposure_increasing_notional_lower_bound": round(total_lower_bound, 6),
            "total_exposure_increasing_notional_upper_bound": round(total_upper_bound, 6),
            "target_coin_exposure_increasing_notional_lower_bound": round(total_target_lower_bound, 6),
            "target_coin_exposure_increasing_notional_upper_bound": round(total_target_upper_bound, 6),
            "off_target_exposure_increasing_notional_lower_bound": round(total_off_target_lower_bound, 6),
            "off_target_exposure_increasing_notional_upper_bound": round(total_off_target_upper_bound, 6),
            "users_with_off_target_bounds": users_with_off_target_bounds,
            "users_with_negative_gap": users_with_negative_gap,
            "users_with_positive_gap": users_with_positive_gap,
        },
        "top_users_by_exposure_increasing_lower_bound": sorted(
            rows,
            key=lambda row: row["exposure_increasing_notional_lower_bound"],
            reverse=True,
        )[: args.top_n],
        "top_users_by_abs_margin_gap": sorted(
            rows,
            key=lambda row: abs(float(row["margin_gap_total"])),
            reverse=True,
        )[: args.top_n],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Reserved-margin proxy report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
