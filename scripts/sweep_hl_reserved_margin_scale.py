#!/usr/bin/env python3
"""Sweep global reserved-margin scale factors against live Hyperliquid liqPx."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.compare_hl_reserved_margin_allocation_modes import _summarize_errors
from scripts.compare_hl_solver_v1_vs_v1_1 import _build_user_state, _load_outlier_orders
from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.margin_math import (
    DEFAULT_RESERVED_MARGIN_CANDIDATE,
    estimate_reserved_margin,
)
from src.liquidationheatmap.hyperliquid.models import AssetMetaSnapshot, ClearinghouseUserState
from src.liquidationheatmap.hyperliquid.sidecar import SidecarPositionReconstructor


@dataclass(frozen=True)
class UserScaleSummary:
    user: str
    mode: str
    scale: float
    positions_compared: int
    improved_positions: int
    worsened_positions: int
    unchanged_positions: int
    improvement_rate: float | None


def _rank_scale_results(results: list[dict]) -> list[dict]:
    return sorted(
        results,
        key=lambda item: (
            item["cross_margin_only"]["improvement_rate"] or 0.0,
            item["cross_margin_only"]["improved_positions"],
            -(item["cross_margin_only"]["worsened_positions"]),
            item["all_accounts"]["improvement_rate"] or 0.0,
        ),
        reverse=True,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep reserved-margin scale factors.")
    parser.add_argument(
        "--outliers",
        default="data/validation/hl_reserved_margin_outliers_eth_sample.json",
        help="Outlier JSON with reconstructed orders.",
    )
    parser.add_argument(
        "--candidate",
        default=DEFAULT_RESERVED_MARGIN_CANDIDATE,
        choices=["A", "B", "C", "D", "E"],
        help="Reserved-margin candidate to scale.",
    )
    parser.add_argument(
        "--scales",
        nargs="+",
        type=float,
        default=[0.1, 0.25, 0.5, 0.75, 1.0],
        help="Scale factors to test.",
    )
    parser.add_argument(
        "--output",
        default="data/validation/reserved_margin_scale_sweep.json",
        help="Output JSON path.",
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
        reserved_margin = estimate_reserved_margin(
            orders,
            args.candidate,
            mark_prices=mark_prices,
            asset_meta=asset_meta,
            current_positions=current_positions,
        )
        cached_users.append(
            {
                "user": user,
                "mode": margin_mode,
                "state": state,
                "user_state": user_state,
                "mark_prices": mark_prices,
                "tiers": tiers,
                "reserved_margin": reserved_margin,
            }
        )

    scale_results = []
    for scale in args.scales:
        all_v1_errors = []
        all_v1_1_errors = []
        cross_v1_errors = []
        cross_v1_1_errors = []
        user_rows = []

        for entry in cached_users:
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
                    reserved_margin=entry["reserved_margin"] * scale,
                )
                if v1 is None or v1_1 is None:
                    continue
                v1_errors.append(abs(v1 - position.liquidationPx))
                v1_1_errors.append(abs(v1_1 - position.liquidationPx))

            summary = _summarize_errors(v1_errors, v1_1_errors, f"scale_{scale}")
            user_rows.append(
                asdict(
                    UserScaleSummary(
                        user=entry["user"],
                        mode=entry["mode"],
                        scale=scale,
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

        scale_results.append(
            {
                "scale": scale,
                "all_accounts": asdict(_summarize_errors(all_v1_errors, all_v1_1_errors, f"scale_{scale}")),
                "cross_margin_only": asdict(
                    _summarize_errors(cross_v1_errors, cross_v1_1_errors, f"scale_{scale}")
                ),
                "users": user_rows,
            }
        )

    ranked = _rank_scale_results(scale_results)
    payload = {
        "candidate": args.candidate,
        "scales": scale_results,
        "ranked": ranked,
        "winner": ranked[0] if ranked else None,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
