"""Margin Validator for Hyperliquid."""

from datetime import datetime, timezone
import asyncio
from typing import List

from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.models import (
    MarginMode, MarginValidationResult, PositionMarginComparison, 
    MarginValidationReport
)
from src.liquidationheatmap.hyperliquid.margin_math import compute_position_maintenance_margin
from src.liquidationheatmap.hyperliquid.sidecar import UserPosition

class MarginValidator:
    def __init__(self, client: HyperliquidInfoClient = None):
        self.client = client or HyperliquidInfoClient()
    
    def detect_margin_mode(self, state: dict) -> MarginMode:
        if state.get("portfolioMarginSummary"):
            return MarginMode.PORTFOLIO_MARGIN
        for ap in state.get("assetPositions", []):
            lev = ap.get("position", {}).get("leverage", {})
            if lev.get("type") == "isolated":
                return MarginMode.ISOLATED_MARGIN
        return MarginMode.CROSS_MARGIN

    async def validate_user(self, user: str) -> MarginValidationResult:
        state = await self.client.get_clearinghouse_state(user)
        meta = await self.client.get_asset_meta()
        
        mode = self.detect_margin_mode(state)
        
        api_total_margin_used = float(state.get("marginSummary", {}).get("totalMarginUsed", "0"))
        api_cross_maintenance_margin_used = float(state.get("crossMaintenanceMarginUsed", "0"))
        
        asset_meta = {}
        for idx, asset in enumerate(meta[0]["universe"]):
            asset_meta[asset["name"]] = {"idx": idx, "szDecimals": asset["szDecimals"]}
        
        # Build marks
        mark_prices = {}
        for idx, ctx in enumerate(meta[1]):
            mark_prices[idx] = float(ctx["markPx"])
            
        positions = []
        sidecar_total_mmr = 0.0
        
        for ap in state.get("assetPositions", []):
            pos_data = ap["position"]
            coin = pos_data["coin"]
            size = float(pos_data["szi"])
            entry_px = float(pos_data["entryPx"])
            api_margin_used = float(pos_data["marginUsed"])
            api_liq_px = pos_data.get("liquidationPx")
            api_liq_px = float(api_liq_px) if api_liq_px else None
            max_leverage = float(pos_data["maxLeverage"])
            
            idx = asset_meta[coin]["idx"]
            mark = mark_prices[idx]
            
            # Simple single-tier reconstruction based on maxLeverage
            mmr_rate = 1.0 / (2.0 * max_leverage) if max_leverage > 0 else 0.01
            tiers = {idx: [{"lower_bound": 0, "mmr_rate": mmr_rate, "maintenance_deduction": 0.0}]}
            
            # Mock UserPosition for the math function
            up = UserPosition(
                coin=coin, asset_idx=idx, size=size, entry_px=entry_px,
                margin=api_margin_used, leverage=max_leverage, cum_funding=0.0
            )
            
            sidecar_mmr = compute_position_maintenance_margin(up, mark_prices, tiers)
            sidecar_total_mmr += sidecar_mmr
            
            positions.append(PositionMarginComparison(
                coin=coin, size=size, entry_px=entry_px, mark_px=mark,
                api_margin_used=api_margin_used, api_liquidation_px=api_liq_px,
                sidecar_mmr=sidecar_mmr, sidecar_liquidation_px_v1=None,
                sidecar_liquidation_px_v1_1=None, deviation_liq_px_v1=None,
                deviation_liq_px_v1_1=None
            ))
            
        if api_cross_maintenance_margin_used > 0:
            deviation_mmr_pct = abs(api_cross_maintenance_margin_used - sidecar_total_mmr) / api_cross_maintenance_margin_used * 100.0
        else:
            deviation_mmr_pct = 0.0
            
        return MarginValidationResult(
            user=user, mode=mode,
            api_total_margin_used=api_total_margin_used,
            api_cross_maintenance_margin_used=api_cross_maintenance_margin_used,
            sidecar_total_mmr=sidecar_total_mmr,
            deviation_mmr_pct=deviation_mmr_pct,
            positions=positions
        )

    async def validate_batch(self, users: List[str]) -> MarginValidationReport:
        results = []
        for user in users:
            results.append(await self.validate_user(user))
            
        mean_deviation = sum(r.deviation_mmr_pct for r in results) / len(results) if results else 0.0
        
        return MarginValidationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            users_analyzed=len(results),
            mean_mmr_deviation_pct=mean_deviation,
            results=results
        )
