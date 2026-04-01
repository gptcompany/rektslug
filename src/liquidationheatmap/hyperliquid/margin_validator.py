import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, List

from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.margin_math import (
    DEFAULT_RESERVED_MARGIN_CANDIDATE,
    compute_position_maintenance_margin,
    estimate_reserved_margin,
)
from src.liquidationheatmap.hyperliquid.models import (
    AccountAbstraction,
    AssetMetaSnapshot,
    BorrowLendUserState,
    ClearinghouseUserState,
    FactorAttribution,
    LiqPxComparisonSummary,
    MarginModeReportSummary,
    MarginMode,
    MarginValidationReport,
    MarginValidationResult,
    PositionMarginComparison,
    SpotClearinghouseState,
)
from src.liquidationheatmap.hyperliquid.portfolio_solver import (
    HyperliquidPortfolioMarginSolver,
)
from src.liquidationheatmap.hyperliquid.sidecar import (
    SidecarPositionReconstructor,
    UserOrder,
    UserPosition,
    UserState,
)

logger = logging.getLogger(__name__)


class MarginValidator:
    def __init__(
        self,
        client: HyperliquidInfoClient = None,
        *,
        orders_by_user: dict[str, list[UserOrder]] | None = None,
        reserved_margin_candidate: str = DEFAULT_RESERVED_MARGIN_CANDIDATE,
    ):
        self.client = client or HyperliquidInfoClient()
        self.reconstructor = SidecarPositionReconstructor()
        self.portfolio_solver = HyperliquidPortfolioMarginSolver()
        self.orders_by_user = orders_by_user or {}
        self.reserved_margin_candidate = reserved_margin_candidate

    @staticmethod
    def _build_liq_px_summary(
        positions: list[PositionMarginComparison],
    ) -> LiqPxComparisonSummary | None:
        comparable_positions = [
            position
            for position in positions
            if position.deviation_liq_px_v1 is not None
        ]
        if not comparable_positions:
            return None

        v1_errors = [position.deviation_liq_px_v1 for position in comparable_positions]
        v1_1_positions = [
            position for position in comparable_positions if position.deviation_liq_px_v1_1 is not None
        ]
        v1_1_errors = [
            position.deviation_liq_px_v1_1 for position in v1_1_positions
        ]

        improved_positions = 0
        worsened_positions = 0
        unchanged_positions = 0
        for position in v1_1_positions:
            if position.deviation_liq_px_v1_1 < position.deviation_liq_px_v1:
                improved_positions += 1
            elif position.deviation_liq_px_v1_1 > position.deviation_liq_px_v1:
                worsened_positions += 1
            else:
                unchanged_positions += 1

        positions_compared = len(v1_1_positions)
        return LiqPxComparisonSummary(
            positions_compared=positions_compared,
            improved_positions=improved_positions,
            worsened_positions=worsened_positions,
            unchanged_positions=unchanged_positions,
            v1_mean_abs_error=(sum(v1_errors) / len(v1_errors)) if v1_errors else None,
            v1_1_mean_abs_error=(sum(v1_1_errors) / len(v1_1_errors)) if v1_1_errors else None,
            improvement_rate=(
                improved_positions / positions_compared if positions_compared else None
            ),
        )

    @staticmethod
    def requires_spot_clearinghouse_state(
        account_abstraction: AccountAbstraction | str | None,
    ) -> bool:
        abstraction = AccountAbstraction.from_api(account_abstraction)
        return abstraction in {
            AccountAbstraction.UNIFIED_ACCOUNT,
            AccountAbstraction.PORTFOLIO_MARGIN,
        }

    def detect_margin_mode(
        self,
        state: ClearinghouseUserState | dict,
        *,
        account_abstraction: AccountAbstraction | str | None = None,
    ) -> MarginMode:
        abstraction = AccountAbstraction.from_api(account_abstraction)
        if abstraction == AccountAbstraction.PORTFOLIO_MARGIN:
            return MarginMode.PORTFOLIO_MARGIN

        if isinstance(state, ClearinghouseUserState):
            if state.portfolioMarginSummary is not None:
                return MarginMode.PORTFOLIO_MARGIN
            leverage_types = [ap.position.leverage.type for ap in state.assetPositions]
            if leverage_types and all(lev_type == "isolated" for lev_type in leverage_types):
                return MarginMode.ISOLATED_MARGIN
            return MarginMode.CROSS_MARGIN

        if state.get("portfolioMarginSummary"):
            return MarginMode.PORTFOLIO_MARGIN
        leverage_types = [
            ap.get("position", {}).get("leverage", {}).get("type")
            for ap in state.get("assetPositions", [])
        ]
        if leverage_types and all(lev_type == "isolated" for lev_type in leverage_types):
                return MarginMode.ISOLATED_MARGIN
        return MarginMode.CROSS_MARGIN

    def attribute_factors(self, deviation_pct: float, gap_usd: float) -> list[FactorAttribution]:
        """Decompose margin deviations exceeding 1% into identifiable factor categories."""
        if deviation_pct <= 1.0 or gap_usd <= 0:
            return []

        factors: list[FactorAttribution] = []

        if deviation_pct <= 1.5:
            factors.append(
                FactorAttribution(
                    category="multi_tier_rounding",
                    estimated_impact_usd=gap_usd,
                    description="Small gap is consistent with tier rounding or mark-price alignment noise.",
                )
            )
            return factors

        funding_component = min(gap_usd * 0.1, 25.0)
        if funding_component > 0:
            factors.append(
                FactorAttribution(
                    category="funding_timing",
                    estimated_impact_usd=funding_component,
                    description="Portion of the gap plausibly explained by funding timing mismatch.",
                )
            )

        reserve_component = max(gap_usd - funding_component, 0.0)
        reserve_estimate = reserve_component * 0.7
        if reserve_estimate > 0:
            factors.append(
                FactorAttribution(
                    category="estimated_resting_order_reserve",
                    estimated_impact_usd=reserve_estimate,
                    description="Best-effort estimate of hidden reserved margin for resting orders.",
                )
            )

        unknown_residual = max(gap_usd - funding_component - reserve_estimate, 0.0)
        if unknown_residual > 0:
            factors.append(
                FactorAttribution(
                    category="unknown",
                    estimated_impact_usd=unknown_residual,
                    description="Residual gap not explained by current heuristics.",
                )
            )

        return factors

    def _estimate_reserved_margin(
        self,
        user: str,
        mark_prices: dict[int, float],
        asset_meta: dict[str, dict],
        current_positions: dict[str, float],
    ) -> float:
        orders = self.orders_by_user.get(user)
        if not orders:
            return 0.0

        return estimate_reserved_margin(
            orders,
            self.reserved_margin_candidate,
            mark_prices=mark_prices,
            asset_meta=asset_meta,
            current_positions=current_positions,
        )

    async def _compute_portfolio_margin_result(
        self,
        *,
        user: str,
        positions: list[UserPosition],
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
        cross_maintenance_margin_used: float,
    ):
        (
            spot_state,
            borrow_lend_user_state,
            reserve_states,
        ) = await asyncio.gather(
            self.client.get_spot_clearinghouse_state(user),
            self.client.get_borrow_lend_user_state(user),
            self.client.get_all_borrow_lend_reserve_states(),
        )
        return self.portfolio_solver.compute_portfolio_margin(
            user_address=user,
            positions=positions,
            mark_prices=mark_prices,
            asset_margin_tiers=asset_margin_tiers,
            spot_state=spot_state,
            cross_maintenance_margin_used=cross_maintenance_margin_used,
            borrow_lend_user_state=borrow_lend_user_state,
            reserve_states=reserve_states,
        )

    async def validate_user(self, user: str) -> MarginValidationResult:
        state: ClearinghouseUserState = await self.client.get_clearinghouse_state(user)
        account_abstraction = await self.client.get_user_abstraction(user)
        meta: AssetMetaSnapshot = await self.client.get_asset_meta()

        mode = self.detect_margin_mode(state, account_abstraction=account_abstraction)

        api_total_margin_used = state.marginSummary.totalMarginUsed
        api_cross_maintenance_margin_used = state.crossMaintenanceMarginUsed
        raw_balance = state.crossMarginSummary.totalRawUsd

        asset_meta_lookup = {
            asset.name: {
                "idx": idx,
                "szDecimals": asset.szDecimals,
                "maxLeverage": asset.maxLeverage,
                "marginTableId": asset.marginTableId,
            }
            for idx, asset in enumerate(meta.universe)
        }
        mark_prices = {
            idx: ctx.markPx
            for idx, ctx in enumerate(meta.assetContexts)
        }

        # Build full asset_margin_tiers map for compute_position_maintenance_margin
        asset_margin_tiers = {}
        for asset_name, info in asset_meta_lookup.items():
            idx = info["idx"]
            table_id = info["marginTableId"]
            if table_id in meta.margin_tables:
                # Convert to dict for sidecar compatibility
                asset_margin_tiers[idx] = [
                    {
                        "lower_bound": t.lower_bound,
                        "mmr_rate": t.mmr_rate,
                        "maintenance_deduction": t.maintenance_deduction,
                    }
                    for t in meta.margin_tables[table_id]
                ]
            else:
                # Fallback to single tier if table not found
                max_lev = info["maxLeverage"]
                mmr_rate = 1.0 / (2.0 * max_lev) if max_lev > 0 else 0.01
                asset_margin_tiers[idx] = [
                    {"lower_bound": 0, "mmr_rate": mmr_rate, "maintenance_deduction": 0.0}
                ]

        positions_cm = []
        sidecar_positions = []
        sidecar_total_mmr = 0.0
        current_positions = {}

        for ap in state.assetPositions:
            pos_data = ap.position
            coin = pos_data.coin
            size = pos_data.szi
            entry_px = pos_data.entryPx
            api_margin_used = pos_data.marginUsed
            api_liq_px = pos_data.liquidationPx
            leverage_type = pos_data.leverage.type

            if coin not in asset_meta_lookup:
                logger.warning("Coin %s not found in asset meta", coin)
                continue

            info = asset_meta_lookup[coin]
            idx = info["idx"]
            mark = mark_prices[idx]

            up = UserPosition(
                coin=coin,
                asset_idx=idx,
                size=size,
                entry_px=entry_px,
                margin=api_margin_used,
                leverage=float(pos_data.maxLeverage),
                cum_funding=pos_data.cumFunding.sinceOpen,
            )
            sidecar_positions.append(up)
            current_positions[coin] = size

            # Use full asset_margin_tiers for MMR calculation
            sidecar_mmr = compute_position_maintenance_margin(up, mark_prices, asset_margin_tiers)
            if mode != MarginMode.CROSS_MARGIN or leverage_type != "isolated":
                sidecar_total_mmr += sidecar_mmr

            positions_cm.append({
                "coin": coin,
                "size": size,
                "entry_px": entry_px,
                "mark_px": mark,
                "api_margin_used": api_margin_used,
                "api_liquidation_px": api_liq_px,
                "sidecar_mmr": sidecar_mmr,
                "asset_margin_tiers": asset_margin_tiers,
            })

        # The liquidation solver consumes raw USD balance (`totalRawUsd`), not account value.
        user_state = UserState(user=user, balance=raw_balance, positions=tuple(sidecar_positions))
        reserved_margin = self._estimate_reserved_margin(
            user,
            mark_prices,
            {
                name: {"idx": info["idx"], "maxLeverage": info["maxLeverage"]}
                for name, info in asset_meta_lookup.items()
            },
            current_positions,
        )
        portfolio_margin_result = None
        if mode == MarginMode.PORTFOLIO_MARGIN:
            portfolio_margin_result = await self._compute_portfolio_margin_result(
                user=user,
                positions=sidecar_positions,
                mark_prices=mark_prices,
                asset_margin_tiers=asset_margin_tiers,
                cross_maintenance_margin_used=api_cross_maintenance_margin_used,
            )
            sidecar_total_mmr = portfolio_margin_result.total_margin_required

        final_positions = []
        for p in positions_cm:
            if portfolio_margin_result is not None:
                sidecar_liq_px_v1 = portfolio_margin_result.liquidation_prices.get(p["coin"])
            else:
                sidecar_liq_px_v1 = self.reconstructor.solve_liquidation_price(
                    user_state, p["coin"], mark_prices, p["asset_margin_tiers"]
                )

            dev_liq_px_v1 = None
            sidecar_liq_px_v1_1 = None
            dev_liq_px_v1_1 = None
            liq_px_dev_pct = None
            if sidecar_liq_px_v1 is not None and p["api_liquidation_px"] is not None:
                dev_liq_px_v1 = abs(sidecar_liq_px_v1 - p["api_liquidation_px"])
                if p["api_liquidation_px"] > 0:
                    liq_px_dev_pct = dev_liq_px_v1 / p["api_liquidation_px"] * 100.0

            if portfolio_margin_result is not None:
                sidecar_liq_px_v1_1 = sidecar_liq_px_v1
            else:
                sidecar_liq_px_v1_1 = self.reconstructor.solve_liquidation_price(
                    user_state,
                    p["coin"],
                    mark_prices,
                    p["asset_margin_tiers"],
                    reserved_margin=reserved_margin,
                )
            if sidecar_liq_px_v1_1 is not None and p["api_liquidation_px"] is not None:
                dev_liq_px_v1_1 = abs(sidecar_liq_px_v1_1 - p["api_liquidation_px"])

            final_positions.append(PositionMarginComparison(
                coin=p["coin"],
                size=p["size"],
                entry_px=p["entry_px"],
                mark_px=p["mark_px"],
                api_margin_used=p["api_margin_used"],
                api_liquidation_px=p["api_liquidation_px"],
                sidecar_mmr=p["sidecar_mmr"],
                sidecar_liquidation_px_v1=sidecar_liq_px_v1,
                sidecar_liquidation_px_v1_1=sidecar_liq_px_v1_1,
                deviation_liq_px_v1=dev_liq_px_v1,
                deviation_liq_px_v1_1=dev_liq_px_v1_1,
                liq_px_deviation_pct=liq_px_dev_pct,
            ))

        api_margin_reference = (
            api_total_margin_used
            if mode == MarginMode.PORTFOLIO_MARGIN
            else api_cross_maintenance_margin_used
        )
        deviation_mmr_pct = 0.0
        gap_usd = abs(api_margin_reference - sidecar_total_mmr)
        if api_margin_reference > 0:
            deviation_mmr_pct = gap_usd / api_margin_reference * 100.0

        factors = self.attribute_factors(deviation_mmr_pct, gap_usd)
        liq_px_summary = self._build_liq_px_summary(final_positions)

        return MarginValidationResult(
            user=user,
            mode=mode,
            account_abstraction=account_abstraction.value,
            api_total_margin_used=api_total_margin_used,
            api_cross_maintenance_margin_used=api_cross_maintenance_margin_used,
            sidecar_total_mmr=sidecar_total_mmr,
            deviation_mmr_pct=deviation_mmr_pct,
            positions=final_positions,
            factors=factors,
            liq_px_summary=liq_px_summary,
        )

    async def validate_batch(
        self,
        users: List[str],
        *,
        progress_callback: Callable[[str, int, int, bool], None] | None = None,
    ) -> MarginValidationReport:
        results = []
        total_users = len(users)
        completed = 0
        for user in users:
            try:
                res = await self.validate_user(user)
                results.append(res)
                completed += 1
                if progress_callback is not None:
                    progress_callback(user, completed, total_users, True)
            except Exception as e:
                logger.warning("Error validating user %s: %s", user, e)
                completed += 1
                if progress_callback is not None:
                    progress_callback(user, completed, total_users, False)

        if not results:
            return MarginValidationReport(
                timestamp=datetime.now(timezone.utc).isoformat(),
                users_analyzed=0,
                tolerance_rate=0.0,
                mean_mmr_deviation_pct=0.0,
                margin_mode_distribution={},
                mode_summaries={},
                results=[],
                liq_px_summary=None,
            )

        mean_deviation = sum(r.deviation_mmr_pct for r in results) / len(results)
        tolerance_rate = sum(1 for r in results if r.deviation_mmr_pct <= 1.0) / len(results)

        mode_dist = {}
        for r in results:
            mode_str = r.mode.value
            mode_dist[mode_str] = mode_dist.get(mode_str, 0) + 1

        mode_summaries = {}
        for mode_str in mode_dist:
            mode_results = [result for result in results if result.mode.value == mode_str]
            mode_positions = [
                position
                for result in mode_results
                for position in result.positions
            ]
            mode_summaries[mode_str] = MarginModeReportSummary(
                users_analyzed=len(mode_results),
                tolerance_rate=(
                    sum(1 for result in mode_results if result.deviation_mmr_pct <= 1.0)
                    / len(mode_results)
                ),
                mean_mmr_deviation_pct=(
                    sum(result.deviation_mmr_pct for result in mode_results) / len(mode_results)
                ),
                liq_px_summary=self._build_liq_px_summary(mode_positions),
            )

        all_positions = [
            position
            for result in results
            for position in result.positions
        ]
        liq_px_summary = self._build_liq_px_summary(all_positions)

        return MarginValidationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            users_analyzed=len(results),
            tolerance_rate=tolerance_rate,
            mean_mmr_deviation_pct=mean_deviation,
            margin_mode_distribution=mode_dist,
            mode_summaries=mode_summaries,
            results=results,
            liq_px_summary=liq_px_summary,
        )
