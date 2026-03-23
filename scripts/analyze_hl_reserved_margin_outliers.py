#!/usr/bin/env python3
"""Expand reserved-margin report outliers into concrete positions and resting orders."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.liquidationheatmap.hyperliquid.sidecar import (
    SidecarPositionReconstructor,
    UserOrder,
    UserState,
    iter_zst_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/validation/hl_reserved_margin_proxy_eth_sample.json"),
        help="Path to a reserved-margin proxy report.",
    )
    parser.add_argument(
        "--order-status-file",
        type=Path,
        help="Override node_order_statuses_by_block hourly .zst file.",
    )
    parser.add_argument(
        "--raw-book-diff-file",
        type=Path,
        help="Override node_raw_book_diffs_by_block hourly .zst file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/validation/hl_reserved_margin_outliers_eth_sample.json"),
        help="Output path.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="How many users to take from each ranking in the source report.",
    )
    return parser.parse_args()


def order_sign(order: UserOrder) -> int | None:
    if order.side == "B":
        return 1
    if order.side == "A":
        return -1
    return None


def classify_order(order: UserOrder, user_state: UserState) -> tuple[str, float]:
    if order.reduce_only:
        return "reduce_only", 0.0

    position_size = 0.0
    for position in user_state.positions:
        if position.coin == order.coin:
            position_size += position.size

    sign = order_sign(order)
    if sign is None:
        return "unknown_side", 0.0
    if position_size == 0:
        return "opening_flat", order.size
    if position_size > 0:
        if sign > 0:
            return "opening_same_side", order.size
        if order.size <= position_size:
            return "reducing_or_closing", 0.0
        return "partially_opening_opposite", order.size - position_size
    if sign < 0:
        return "opening_same_side", order.size
    if order.size <= abs(position_size):
        return "reducing_or_closing", 0.0
    return "partially_opening_opposite", order.size - abs(position_size)


def main() -> int:
    args = parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    metadata = report["metadata"]
    target_coin = metadata["target_coin"]
    order_status_file = Path(args.order_status_file or metadata["order_status_file"])
    raw_book_diff_file = Path(args.raw_book_diff_file or metadata["raw_book_diff_file"])
    source_anchor = Path(metadata["source_anchor"])

    selected_rows: dict[str, dict] = {}
    ranking_sources = {
        "top_exposure_lower_bound": report.get("top_users_by_exposure_increasing_lower_bound", [])[: args.top_n],
        "top_abs_margin_gap": report.get("top_users_by_abs_margin_gap", [])[: args.top_n],
    }
    for ranking_name, rows in ranking_sources.items():
        for rank, row in enumerate(rows, start=1):
            user = row["user"]
            selected = selected_rows.setdefault(user, {"report_row": row, "rankings": []})
            selected["rankings"].append({"ranking": ranking_name, "rank": rank})

    target_users = set(selected_rows)
    reconstructor = SidecarPositionReconstructor()
    sidecar_state = reconstructor.load_abci_anchor(
        source_anchor,
        target_coin=target_coin,
        target_users=target_users,
    )
    orders_by_user = reconstructor.reconstruct_resting_orders_from_blocks(
        order_status_blocks=iter_zst_jsonl(order_status_file),
        raw_book_diff_blocks=iter_zst_jsonl(raw_book_diff_file),
        target_users=target_users,
    )

    users_output = []
    for user in sorted(target_users):
        user_state = sidecar_state.users.get(user)
        if user_state is None:
            continue
        orders = orders_by_user.get(user, ())
        bounds = reconstructor.compute_resting_order_exposure_bounds(
            user_state,
            orders,
            target_coin=target_coin,
        )
        positions = []
        for position in sorted(user_state.positions, key=lambda p: (p.coin, p.asset_idx)):
            mark_px = sidecar_state.mark_prices.get(position.asset_idx)
            positions.append(
                {
                    "coin": position.coin,
                    "size": round(position.size, 10),
                    "entry_px": round(position.entry_px, 6),
                    "mark_px": round(mark_px, 6) if mark_px is not None else None,
                    "margin": round(position.margin, 6),
                    "maintenance_margin": round(
                        reconstructor.compute_position_maintenance_margin(
                            position,
                            sidecar_state.mark_prices,
                            sidecar_state.asset_margin_tiers,
                        ),
                        6,
                    ),
                }
            )

        order_rows = []
        for order in orders:
            classification, opening_size = classify_order(order, user_state)
            coin_position_size = sum(
                position.size for position in user_state.positions if position.coin == order.coin
            )
            order_rows.append(
                {
                    "oid": order.oid,
                    "coin": order.coin,
                    "side": order.side,
                    "size": round(order.size, 10),
                    "orig_size": round(order.orig_size, 10) if order.orig_size is not None else None,
                    "limit_px": round(order.limit_px, 6),
                    "notional": round(order.size * order.limit_px, 6),
                    "position_size": round(coin_position_size, 10),
                    "classification": classification,
                    "opening_size_upper_bound": round(opening_size, 10),
                    "reduce_only": order.reduce_only,
                    "is_trigger": order.is_trigger,
                    "is_position_tpsl": order.is_position_tpsl,
                    "order_type": order.order_type,
                    "tif": order.tif,
                    "status": order.status,
                }
            )

        users_output.append(
            {
                "user": user,
                "rankings": selected_rows[user]["rankings"],
                "report_row": selected_rows[user]["report_row"],
                "bounds_recomputed": {
                    "exposure_increasing_notional_lower_bound": bounds.exposure_increasing_notional_lower_bound,
                    "exposure_increasing_notional_upper_bound": bounds.exposure_increasing_notional_upper_bound,
                    "target_coin_exposure_increasing_lower_bound": bounds.target_coin_exposure_increasing_lower_bound,
                    "off_target_exposure_increasing_lower_bound": bounds.off_target_exposure_increasing_lower_bound,
                },
                "positions": positions,
                "orders": order_rows,
            }
        )

    result = {
        "metadata": {
            "source_report": str(args.report),
            "source_anchor": str(source_anchor),
            "order_status_file": str(order_status_file),
            "raw_book_diff_file": str(raw_book_diff_file),
            "target_coin": target_coin,
            "selected_user_count": len(users_output),
            "selection_top_n_per_ranking": args.top_n,
        },
        "users": users_output,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Reserved-margin outlier report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
