#!/usr/bin/env python3
"""Compare Hyperliquid solver V1 and V1.1 against live API liquidation prices."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass

from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.margin_math import estimate_reserved_margin
from src.liquidationheatmap.hyperliquid.models import AssetMetaSnapshot, ClearinghouseUserState
from src.liquidationheatmap.hyperliquid.sidecar import (
    SidecarPositionReconstructor,
    UserOrder,
    UserPosition,
    UserState,
)


@dataclass(frozen=True)
class PositionComparison:
    coin: str
    api_liquidation_px: float | None
    v1_liquidation_px: float | None
    v1_1_liquidation_px: float | None
    v1_abs_error: float | None
    v1_1_abs_error: float | None
    improved: bool | None


@dataclass(frozen=True)
class UserComparison:
    user: str
    mode: str
    reserved_margin_candidate: str
    reserved_margin_estimate: float
    improved_positions: int
    worsened_positions: int
    unchanged_positions: int
    positions: list[PositionComparison]


def _load_outlier_orders(path: str) -> dict[str, list[UserOrder]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    users = payload.get("users", []) if isinstance(payload, dict) else []
    result: dict[str, list[UserOrder]] = {}
    for user_data in users:
        user = user_data.get("user")
        if not user:
            continue
        orders = []
        for order in user_data.get("orders", []):
            orders.append(
                UserOrder(
                    user=user,
                    oid=int(order["oid"]),
                    coin=str(order["coin"]),
                    side=str(order["side"]),
                    limit_px=float(order["limit_px"]),
                    size=float(order["size"]),
                    orig_size=float(order["orig_size"]) if order.get("orig_size") is not None else None,
                    tif=order.get("tif"),
                    order_type=order.get("order_type"),
                    reduce_only=bool(order.get("reduce_only", False)),
                    is_trigger=bool(order.get("is_trigger", False)),
                    is_position_tpsl=bool(order.get("is_position_tpsl", False)),
                    status=order.get("status"),
                )
            )
        result[user] = orders
    return result


def _build_user_state(
    user: str,
    state: ClearinghouseUserState,
    meta: AssetMetaSnapshot,
) -> tuple[UserState, dict[int, float], dict[int, list[dict]], dict[str, dict], dict[str, float]]:
    asset_meta = {
        asset.name: {"idx": idx, "maxLeverage": asset.maxLeverage}
        for idx, asset in enumerate(meta.universe)
    }
    mark_prices = {idx: ctx.markPx for idx, ctx in enumerate(meta.assetContexts)}

    tiers = {}
    positions = []
    current_positions = {}
    for api_position in state.assetPositions:
        position = api_position.position
        idx = asset_meta[position.coin]["idx"]
        max_leverage = float(position.maxLeverage)
        tiers[idx] = [
            {
                "lower_bound": 0.0,
                "mmr_rate": 1.0 / (2.0 * max_leverage) if max_leverage > 0 else 0.01,
                "maintenance_deduction": 0.0,
            }
        ]
        positions.append(
            UserPosition(
                coin=position.coin,
                asset_idx=idx,
                size=position.szi,
                entry_px=position.entryPx,
                leverage=float(position.maxLeverage),
                cum_funding=position.cumFunding.sinceOpen,
                margin=position.marginUsed,
            )
        )
        current_positions[position.coin] = position.szi

    user_state = UserState(
        user=user,
        balance=state.marginSummary.accountValue,
        positions=tuple(positions),
    )
    return user_state, mark_prices, tiers, asset_meta, current_positions


async def _compare_user(
    user: str,
    orders: list[UserOrder],
    *,
    client: HyperliquidInfoClient,
    reconstructor: SidecarPositionReconstructor,
    candidate: str,
) -> UserComparison:
    state = await client.get_clearinghouse_state(user)
    meta = await client.get_asset_meta()

    user_state, mark_prices, tiers, asset_meta, current_positions = _build_user_state(
        user, state, meta
    )
    reserved_margin = estimate_reserved_margin(
        orders,
        candidate,
        mark_prices=mark_prices,
        asset_meta=asset_meta,
        current_positions=current_positions,
    )
    mode = "portfolio_margin"
    if state.portfolioMarginSummary is None:
        mode = (
            "isolated_margin"
            if any(position.position.leverage.type == "isolated" for position in state.assetPositions)
            else "cross_margin"
        )

    improved = worsened = unchanged = 0
    position_comparisons: list[PositionComparison] = []
    for api_position in state.assetPositions:
        position = api_position.position
        if position.liquidationPx is None:
            continue

        v1 = reconstructor.solve_liquidation_price(user_state, position.coin, mark_prices, tiers)
        v1_1 = reconstructor.solve_liquidation_price(
            user_state,
            position.coin,
            mark_prices,
            tiers,
            reserved_margin=reserved_margin,
        )
        v1_err = abs(v1 - position.liquidationPx) if v1 is not None else None
        v1_1_err = abs(v1_1 - position.liquidationPx) if v1_1 is not None else None

        improved_flag = None
        if v1_err is not None and v1_1_err is not None:
            if v1_1_err < v1_err:
                improved += 1
                improved_flag = True
            elif v1_1_err > v1_err:
                worsened += 1
                improved_flag = False
            else:
                unchanged += 1

        position_comparisons.append(
            PositionComparison(
                coin=position.coin,
                api_liquidation_px=position.liquidationPx,
                v1_liquidation_px=v1,
                v1_1_liquidation_px=v1_1,
                v1_abs_error=v1_err,
                v1_1_abs_error=v1_1_err,
                improved=improved_flag,
            )
        )

    return UserComparison(
        user=user,
        mode=mode,
        reserved_margin_candidate=candidate,
        reserved_margin_estimate=reserved_margin,
        improved_positions=improved,
        worsened_positions=worsened,
        unchanged_positions=unchanged,
        positions=position_comparisons,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Hyperliquid solver V1 vs V1.1.")
    parser.add_argument(
        "--outliers",
        default="data/validation/hl_reserved_margin_outliers_eth_sample.json",
        help="Outlier JSON with reconstructed orders.",
    )
    parser.add_argument(
        "--output",
        default="data/validation/solver_v1_vs_v1.1_comparison.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--candidate",
        default="A",
        choices=["A", "B", "C", "D"],
        help="Reserved-margin candidate to apply.",
    )
    args = parser.parse_args()

    orders_by_user = _load_outlier_orders(args.outliers)
    client = HyperliquidInfoClient()
    reconstructor = SidecarPositionReconstructor()

    results = []
    for user, orders in orders_by_user.items():
        results.append(
            await _compare_user(
                user,
                orders,
                client=client,
                reconstructor=reconstructor,
                candidate=args.candidate,
            )
        )

    total_positions = sum(len(result.positions) for result in results)
    improved_positions = sum(result.improved_positions for result in results)
    worsened_positions = sum(result.worsened_positions for result in results)
    unchanged_positions = sum(result.unchanged_positions for result in results)
    payload = {
        "candidate": args.candidate,
        "user_count": len(results),
        "positions_compared": total_positions,
        "improved_positions": improved_positions,
        "worsened_positions": worsened_positions,
        "unchanged_positions": unchanged_positions,
        "improvement_rate": (
            improved_positions / total_positions if total_positions else 0.0
        ),
        "results": [asdict(result) for result in results],
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(json.dumps({
        "candidate": payload["candidate"],
        "user_count": payload["user_count"],
        "positions_compared": payload["positions_compared"],
        "improved_positions": payload["improved_positions"],
        "worsened_positions": payload["worsened_positions"],
        "improvement_rate": payload["improvement_rate"],
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
