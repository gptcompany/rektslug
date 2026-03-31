#!/usr/bin/env python3
"""Compare reserved-margin netting modes against live Hyperliquid liqPx."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

from scripts.compare_hl_reserved_margin_allocation_modes import _summarize_errors
from scripts.compare_hl_solver_v1_vs_v1_1 import _build_user_state, _load_outlier_orders
from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.margin_math import (
    DEFAULT_RESERVED_MARGIN_CANDIDATE,
    compute_position_maintenance_margin,
    estimate_reserved_margin,
)
from src.liquidationheatmap.hyperliquid.models import AssetMetaSnapshot, ClearinghouseUserState
from src.liquidationheatmap.hyperliquid.sidecar import SidecarPositionReconstructor, UserOrder


@dataclass(frozen=True)
class UserNettingSummary:
    user: str
    mode: str
    netting_mode: str
    reserved_margin_estimate: float
    positions_compared: int
    improved_positions: int
    worsened_positions: int
    unchanged_positions: int
    improvement_rate: float | None


def _rank_netting_results(results: list[dict]) -> list[dict]:
    return sorted(
        results,
        key=lambda item: (
            item["cross_margin_only"]["improvement_rate"] or 0.0,
            item["cross_margin_only"]["improved_positions"],
            -(item["cross_margin_only"]["worsened_positions"]),
            -(item["cross_margin_only"]["v1_1_mean_abs_error"] or float("inf")),
            item["all_accounts"]["improvement_rate"] or 0.0,
        ),
        reverse=True,
    )


def _coin_order_summaries(
    orders: list[UserOrder],
    *,
    mark_prices: dict[int, float],
    asset_meta: dict[str, dict],
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for order in orders:
        if order.reduce_only or order.coin not in asset_meta:
            continue
        idx = asset_meta[order.coin]["idx"]
        mark = mark_prices.get(idx, 0.0)
        notional = order.size * mark
        summary = result.setdefault(
            order.coin,
            {
                "buy_size": 0.0,
                "sell_size": 0.0,
                "buy_notional": 0.0,
                "sell_notional": 0.0,
            },
        )
        if order.side == "B":
            summary["buy_size"] += order.size
            summary["buy_notional"] += notional
        else:
            summary["sell_size"] += order.size
            summary["sell_notional"] += notional
    return result


def _build_position(asset_idx: int, size: float, entry_px: float) -> SimpleNamespace:
    return SimpleNamespace(asset_idx=asset_idx, size=size, entry_px=entry_px)


def _estimate_side_max_per_order_mmr(
    orders: list[UserOrder],
    *,
    mark_prices: dict[int, float],
    asset_meta: dict[str, dict],
) -> float:
    total_reserve = 0.0
    for coin, summary in _coin_order_summaries(orders, mark_prices=mark_prices, asset_meta=asset_meta).items():
        max_leverage = float(asset_meta[coin]["maxLeverage"])
        mmr_rate = 1.0 / (2.0 * max_leverage) if max_leverage > 0 else 0.0
        total_reserve += max(summary["buy_notional"], summary["sell_notional"]) * mmr_rate
    return total_reserve


def _estimate_net_delta_mmr(
    orders: list[UserOrder],
    *,
    mark_prices: dict[int, float],
    asset_meta: dict[str, dict],
    current_positions: dict[str, float],
    asset_margin_tiers: dict[int, list[dict]],
) -> float:
    total_reserve = 0.0
    for coin, summary in _coin_order_summaries(orders, mark_prices=mark_prices, asset_meta=asset_meta).items():
        idx = asset_meta[coin]["idx"]
        mark = mark_prices.get(idx, 0.0)
        current_size = current_positions.get(coin, 0.0)
        current_margin = compute_position_maintenance_margin(
            _build_position(idx, current_size, mark),
            mark_prices,
            asset_margin_tiers,
        )
        buy_margin = compute_position_maintenance_margin(
            _build_position(idx, current_size + summary["buy_size"], mark),
            mark_prices,
            asset_margin_tiers,
        )
        sell_margin = compute_position_maintenance_margin(
            _build_position(idx, current_size - summary["sell_size"], mark),
            mark_prices,
            asset_margin_tiers,
        )
        total_reserve += max(0.0, max(buy_margin, sell_margin) - current_margin)
    return total_reserve


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare reserved-margin netting modes.")
    parser.add_argument(
        "--outliers",
        default="data/validation/hl_reserved_margin_outliers_eth_sample.json",
        help="Outlier JSON with reconstructed orders.",
    )
    parser.add_argument(
        "--candidate",
        default=DEFAULT_RESERVED_MARGIN_CANDIDATE,
        choices=["A", "B", "C", "D", "E"],
        help="Baseline reserved-margin candidate for current model.",
    )
    parser.add_argument(
        "--output",
        default="data/validation/reserved_margin_netting_modes.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Multiplier applied to each reserved-margin estimate before solving liqPx.",
    )
    args = parser.parse_args()

    orders_by_user = _load_outlier_orders(args.outliers)
    client = HyperliquidInfoClient()
    reconstructor = SidecarPositionReconstructor()
    meta: AssetMetaSnapshot = await client.get_asset_meta()

    cached_users = []
    for user, orders in orders_by_user.items():
        state: ClearinghouseUserState = await client.get_clearinghouse_state(user)
        user_state, mark_prices, tiers, asset_meta, current_positions = _build_user_state(user, state, meta)
        margin_mode = (
            "portfolio_margin"
            if state.portfolioMarginSummary is not None
            else (
                "isolated_margin"
                if any(position.position.leverage.type == "isolated" for position in state.assetPositions)
                else "cross_margin"
            )
        )
        cached_users.append(
            {
                "user": user,
                "orders": orders,
                "mode": margin_mode,
                "state": state,
                "user_state": user_state,
                "mark_prices": mark_prices,
                "tiers": tiers,
                "asset_meta": asset_meta,
                "current_positions": current_positions,
            }
        )

    netting_modes = {
        "per_order_mmr": lambda entry: estimate_reserved_margin(
            entry["orders"],
            args.candidate,
            mark_prices=entry["mark_prices"],
            asset_meta=entry["asset_meta"],
            current_positions=entry["current_positions"],
        ),
        "side_max_per_order_mmr": lambda entry: _estimate_side_max_per_order_mmr(
            entry["orders"],
            mark_prices=entry["mark_prices"],
            asset_meta=entry["asset_meta"],
        ),
        "net_delta_mmr": lambda entry: _estimate_net_delta_mmr(
            entry["orders"],
            mark_prices=entry["mark_prices"],
            asset_meta=entry["asset_meta"],
            current_positions=entry["current_positions"],
            asset_margin_tiers=entry["tiers"],
        ),
    }

    results = []
    for netting_mode, estimate_fn in netting_modes.items():
        all_v1_errors = []
        all_v1_1_errors = []
        cross_v1_errors = []
        cross_v1_1_errors = []
        user_rows = []

        for entry in cached_users:
            reserved_margin = estimate_fn(entry) * args.scale
            v1_errors = []
            v1_1_errors = []
            for api_position in entry["state"].assetPositions:
                position = api_position.position
                if position.liquidationPx is None:
                    continue
                v1 = reconstructor.solve_liquidation_price(
                    entry["user_state"],
                    position.coin,
                    entry["mark_prices"],
                    entry["tiers"],
                )
                v1_1 = reconstructor.solve_liquidation_price(
                    entry["user_state"],
                    position.coin,
                    entry["mark_prices"],
                    entry["tiers"],
                    reserved_margin=reserved_margin,
                )
                if v1 is None or v1_1 is None:
                    continue
                v1_errors.append(abs(v1 - position.liquidationPx))
                v1_1_errors.append(abs(v1_1 - position.liquidationPx))

            summary = _summarize_errors(v1_errors, v1_1_errors, netting_mode)
            user_rows.append(
                asdict(
                    UserNettingSummary(
                        user=entry["user"],
                        mode=entry["mode"],
                        netting_mode=netting_mode,
                        reserved_margin_estimate=reserved_margin,
                        positions_compared=summary.positions_compared,
                        improved_positions=summary.improved_positions,
                        worsened_positions=summary.worsened_positions,
                        unchanged_positions=summary.unchanged_positions,
                        improvement_rate=summary.improvement_rate,
                    )
                )
            )
            all_v1_errors.extend(v1_errors)
            all_v1_1_errors.extend(v1_1_errors)
            if entry["mode"] == "cross_margin":
                cross_v1_errors.extend(v1_errors)
                cross_v1_1_errors.extend(v1_1_errors)

        results.append(
            {
                "netting_mode": netting_mode,
                "all_accounts": asdict(_summarize_errors(all_v1_errors, all_v1_1_errors, netting_mode)),
                "cross_margin_only": asdict(
                    _summarize_errors(cross_v1_errors, cross_v1_1_errors, netting_mode)
                ),
                "users": user_rows,
            }
        )

    ranked = _rank_netting_results(results)
    payload = {
        "candidate": args.candidate,
        "scale": args.scale,
        "results": results,
        "ranked": ranked,
        "winner": ranked[0] if ranked else None,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
