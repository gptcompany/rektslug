#!/usr/bin/env python3
"""Compare reserved-margin allocation modes against live Hyperliquid liqPx."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.compare_hl_solver_v1_vs_v1_1 import _build_user_state, _load_outlier_orders
from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.margin_math import (
    DEFAULT_RESERVED_MARGIN_CANDIDATE,
    estimate_reserved_margin,
)
from src.liquidationheatmap.hyperliquid.models import AssetMetaSnapshot, ClearinghouseUserState
from src.liquidationheatmap.hyperliquid.sidecar import SidecarPositionReconstructor, UserOrder


@dataclass(frozen=True)
class ModeSummary:
    mode: str
    positions_compared: int
    improved_positions: int
    worsened_positions: int
    unchanged_positions: int
    v1_mean_abs_error: float | None
    v1_1_mean_abs_error: float | None
    improvement_rate: float | None


@dataclass(frozen=True)
class UserModeComparison:
    user: str
    mode: str
    allocation_mode: str
    positions_compared: int
    improved_positions: int
    worsened_positions: int
    unchanged_positions: int
    improvement_rate: float | None


def _summarize_errors(v1_errors: list[float], v1_1_errors: list[float], mode: str) -> ModeSummary:
    improved = worsened = unchanged = 0
    for v1_error, v1_1_error in zip(v1_errors, v1_1_errors):
        if v1_1_error < v1_error:
            improved += 1
        elif v1_1_error > v1_error:
            worsened += 1
        else:
            unchanged += 1

    positions_compared = len(v1_errors)
    return ModeSummary(
        mode=mode,
        positions_compared=positions_compared,
        improved_positions=improved,
        worsened_positions=worsened,
        unchanged_positions=unchanged,
        v1_mean_abs_error=(sum(v1_errors) / positions_compared) if positions_compared else None,
        v1_1_mean_abs_error=(sum(v1_1_errors) / positions_compared) if positions_compared else None,
        improvement_rate=(improved / positions_compared) if positions_compared else None,
    )


def _estimate_reserved_margin_for_coin(
    coin: str,
    all_orders: list[UserOrder],
    *,
    candidate: str,
    mark_prices: dict[int, float],
    asset_meta: dict[str, dict],
    current_positions: dict[str, float],
) -> float:
    coin_orders = [order for order in all_orders if order.coin == coin]
    if not coin_orders:
        return 0.0
    return estimate_reserved_margin(
        coin_orders,
        candidate,
        mark_prices=mark_prices,
        asset_meta=asset_meta,
        current_positions=current_positions,
    )


def _sum_opening_notional_for_coin(
    coin: str,
    orders: list[UserOrder],
    *,
    mark_prices: dict[int, float],
    asset_meta: dict[str, dict],
) -> float:
    if coin not in asset_meta:
        return 0.0
    idx = asset_meta[coin]["idx"]
    mark = mark_prices.get(idx, 0.0)
    return sum(order.size * mark for order in orders if not order.reduce_only and order.coin == coin)


async def _compare_user(
    user: str,
    orders: list[UserOrder],
    *,
    client: HyperliquidInfoClient,
    reconstructor: SidecarPositionReconstructor,
    candidate: str,
    allocation_mode: str,
) -> tuple[UserModeComparison, list[float], list[float], str]:
    state: ClearinghouseUserState = await client.get_clearinghouse_state(user)
    meta: AssetMetaSnapshot = await client.get_asset_meta()
    user_state, mark_prices, tiers, asset_meta, current_positions = _build_user_state(user, state, meta)

    if state.portfolioMarginSummary is None:
        margin_mode = (
            "isolated_margin"
            if any(position.position.leverage.type == "isolated" for position in state.assetPositions)
            else "cross_margin"
        )
    else:
        margin_mode = "portfolio_margin"

    global_reserved_margin = estimate_reserved_margin(
        orders,
        candidate,
        mark_prices=mark_prices,
        asset_meta=asset_meta,
        current_positions=current_positions,
    )

    v1_errors: list[float] = []
    v1_1_errors: list[float] = []
    for api_position in state.assetPositions:
        position = api_position.position
        if position.liquidationPx is None:
            continue

        if allocation_mode == "global":
            reserved_margin = global_reserved_margin
        elif allocation_mode == "target_coin_only":
            reserved_margin = _estimate_reserved_margin_for_coin(
                position.coin,
                orders,
                candidate=candidate,
                mark_prices=mark_prices,
                asset_meta=asset_meta,
                current_positions=current_positions,
            )
        elif allocation_mode == "target_coin_weighted":
            total_notional = sum(
                _sum_opening_notional_for_coin(
                    coin,
                    orders,
                    mark_prices=mark_prices,
                    asset_meta=asset_meta,
                )
                for coin in {order.coin for order in orders if not order.reduce_only}
            )
            target_notional = _sum_opening_notional_for_coin(
                position.coin,
                orders,
                mark_prices=mark_prices,
                asset_meta=asset_meta,
            )
            reserved_margin = (
                global_reserved_margin * (target_notional / total_notional)
                if total_notional > 0
                else 0.0
            )
        else:
            raise ValueError(f"Unsupported allocation mode: {allocation_mode}")

        v1 = reconstructor.solve_liquidation_price(user_state, position.coin, mark_prices, tiers)
        v1_1 = reconstructor.solve_liquidation_price(
            user_state,
            position.coin,
            mark_prices,
            tiers,
            reserved_margin=reserved_margin,
        )
        if v1 is None or v1_1 is None:
            continue

        v1_errors.append(abs(v1 - position.liquidationPx))
        v1_1_errors.append(abs(v1_1 - position.liquidationPx))

    summary = _summarize_errors(v1_errors, v1_1_errors, allocation_mode)
    return (
        UserModeComparison(
            user=user,
            mode=margin_mode,
            allocation_mode=allocation_mode,
            positions_compared=summary.positions_compared,
            improved_positions=summary.improved_positions,
            worsened_positions=summary.worsened_positions,
            unchanged_positions=summary.unchanged_positions,
            improvement_rate=summary.improvement_rate,
        ),
        v1_errors,
        v1_1_errors,
        margin_mode,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare global vs target-coin reserved-margin allocation modes."
    )
    parser.add_argument(
        "--outliers",
        default="data/validation/hl_reserved_margin_outliers_eth_sample.json",
        help="Outlier JSON with reconstructed orders.",
    )
    parser.add_argument(
        "--candidate",
        default=DEFAULT_RESERVED_MARGIN_CANDIDATE,
        choices=["A", "B", "C", "D"],
        help="Reserved-margin candidate used for both allocation modes.",
    )
    parser.add_argument(
        "--output",
        default="data/validation/reserved_margin_allocation_modes.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()

    orders_by_user = _load_outlier_orders(args.outliers)
    client = HyperliquidInfoClient()
    reconstructor = SidecarPositionReconstructor()

    payload: dict[str, object] = {
        "candidate": args.candidate,
        "modes": {},
    }
    allocation_modes = ["global", "target_coin_only", "target_coin_weighted"]

    for allocation_mode in allocation_modes:
        user_rows: list[dict] = []
        all_v1_errors: list[float] = []
        all_v1_1_errors: list[float] = []
        cross_v1_errors: list[float] = []
        cross_v1_1_errors: list[float] = []

        for user, orders in orders_by_user.items():
            user_summary, v1_errors, v1_1_errors, margin_mode = await _compare_user(
                user,
                orders,
                client=client,
                reconstructor=reconstructor,
                candidate=args.candidate,
                allocation_mode=allocation_mode,
            )
            user_rows.append(asdict(user_summary))
            all_v1_errors.extend(v1_errors)
            all_v1_1_errors.extend(v1_1_errors)
            if margin_mode == "cross_margin":
                cross_v1_errors.extend(v1_errors)
                cross_v1_1_errors.extend(v1_1_errors)

        payload["modes"][allocation_mode] = {
            "all_accounts": asdict(_summarize_errors(all_v1_errors, all_v1_1_errors, allocation_mode)),
            "cross_margin_only": asdict(
                _summarize_errors(cross_v1_errors, cross_v1_1_errors, allocation_mode)
            ),
            "users": user_rows,
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
