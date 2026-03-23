#!/usr/bin/env python3
"""Reconstruct bounded resting-order state for sidecar-relevant Hyperliquid users."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
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
        default=Path("data/validation/hl_order_state_reconstruction_eth_sample.json"),
        help="Output path.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="How many top active orders/users to retain in the report.",
    )
    return parser.parse_args()


def parse_analysis_end(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def summarize_orders(orders_by_user: dict[str, tuple], target_coin: str) -> dict:
    active_orders: list[dict] = []
    user_rows: list[dict] = []
    coin_breakdown: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"order_count": 0, "user_count": 0, "total_size": 0.0, "total_notional": 0.0}
    )
    coin_users: dict[str, set[str]] = defaultdict(set)

    for user, orders in orders_by_user.items():
        user_notional = 0.0
        user_target_notional = 0.0
        user_coins = set()
        for order in orders:
            notional = order.size * order.limit_px
            active_orders.append(
                {
                    "user": user,
                    "oid": order.oid,
                    "coin": order.coin,
                    "side": order.side,
                    "limit_px": round(order.limit_px, 10),
                    "size": round(order.size, 10),
                    "orig_size": round(order.orig_size, 10) if order.orig_size is not None else None,
                    "notional": round(notional, 6),
                    "tif": order.tif,
                    "order_type": order.order_type,
                    "reduce_only": order.reduce_only,
                    "status": order.status,
                    "order_timestamp_ms": order.order_timestamp_ms,
                }
            )
            stats = coin_breakdown[order.coin]
            stats["order_count"] += 1
            stats["total_size"] += order.size
            stats["total_notional"] += notional
            coin_users[order.coin].add(user)
            user_notional += notional
            if order.coin == target_coin:
                user_target_notional += notional
            user_coins.add(order.coin)

        user_rows.append(
            {
                "user": user,
                "order_count": len(orders),
                "coins": sorted(user_coins),
                "total_notional": round(user_notional, 6),
                "target_coin_notional": round(user_target_notional, 6),
                "has_off_target_orders": any(coin != target_coin for coin in user_coins),
            }
        )

    for coin, users in coin_users.items():
        coin_breakdown[coin]["user_count"] = len(users)

    return {
        "active_order_count": len(active_orders),
        "active_user_count": len(orders_by_user),
        "coin_breakdown": {
            coin: {
                "order_count": int(stats["order_count"]),
                "user_count": int(stats["user_count"]),
                "total_size": round(float(stats["total_size"]), 6),
                "total_notional": round(float(stats["total_notional"]), 6),
            }
            for coin, stats in sorted(coin_breakdown.items())
        },
        "top_orders_by_notional": sorted(active_orders, key=lambda row: row["notional"], reverse=True),
        "top_users_by_notional": sorted(user_rows, key=lambda row: row["total_notional"], reverse=True),
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
    sidecar_state = builder.reconstruct(request)
    reconstructor = SidecarPositionReconstructor()

    order_status_blocks = iter_zst_jsonl(args.order_status_file)
    raw_book_diff_blocks = iter_zst_jsonl(args.raw_book_diff_file)
    orders_by_user = reconstructor.reconstruct_resting_orders_from_blocks(
        order_status_blocks=order_status_blocks,
        raw_book_diff_blocks=raw_book_diff_blocks,
        target_users=set(sidecar_state.users),
    )
    summary = summarize_orders(orders_by_user, request.target_coin)

    result = {
        "metadata": {
            "symbol": request.symbol,
            "target_coin": request.target_coin,
            "timeframe_days": request.timeframe_days,
            "analysis_end_utc": request.analysis_end.isoformat(),
            "source_anchor": str(plan.anchor_coverage.latest_anchor_in_window),
            "order_status_file": str(args.order_status_file),
            "raw_book_diff_file": str(args.raw_book_diff_file),
            "target_user_count": len(sidecar_state.users),
            "order_status_block_count": None,
            "raw_book_diff_block_count": None,
        },
        "summary": {
            "active_order_count": summary["active_order_count"],
            "active_user_count": summary["active_user_count"],
            "active_target_coin_order_count": sum(
                1
                for row in summary["top_orders_by_notional"]
                if row["coin"] == request.target_coin
            ),
            "active_off_target_order_count": sum(
                1
                for row in summary["top_orders_by_notional"]
                if row["coin"] != request.target_coin
            ),
            "users_with_off_target_orders": sum(
                1
                for row in summary["top_users_by_notional"]
                if row["has_off_target_orders"]
            ),
        },
        "coin_breakdown": summary["coin_breakdown"],
        "top_orders_by_notional": summary["top_orders_by_notional"][: args.top_n],
        "top_users_by_notional": summary["top_users_by_notional"][: args.top_n],
        "limitations": [
            "Only the supplied retained blocks are reconstructed; carry-in resting orders from earlier files are not inferred.",
            "This artifact reconstructs visible resting orders, not reserved-margin semantics or open-order maintenance impact.",
            "Target-user filtering comes from the latest retained sidecar anchor in the requested window.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Order-state reconstruction written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
