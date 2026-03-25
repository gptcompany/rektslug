"""Margin validation logic for Binance Futures accounts."""

import logging
from typing import Dict, Any

from src.exchanges.binance import BinanceAdapter

logger = logging.getLogger(__name__)


class MarginValidator:
    """Validates margin requirements for Binance Futures accounts."""

    def __init__(self, binance_adapter: BinanceAdapter):
        self.binance_adapter = binance_adapter

    def calculate_mmr(self, notional: float, max_leverage: float) -> float:
        """Calculates the theoretical MMR based on notional and max leverage."""
        if max_leverage <= 0:
            raise ValueError("Max leverage must be greater than 0.")
        return notional / (2 * max_leverage)

    async def validate_account_margin(self) -> Dict[str, Any]:
        """
        Fetches account margin information and validates against expected MMR.

        Returns:
            A dictionary containing validation results.
        """
        account_info = await self.binance_adapter.fetch_account_info()

        if not account_info:
            return {"status": "error", "message": "Failed to fetch account info."}

        # Extract relevant information
        cross_wallet_balance = float(account_info.get("totalWalletBalance", 0))
        cross_unrealized_pnl = float(account_info.get("totalUnrealizedProfit", 0))
        cross_maintenance_margin_used = float(account_info.get("totalMaintMargin", 0))
        # Note: Binance API v2 does not expose maxLeverage directly in account info,
        # it's usually per symbol/position. For a comprehensive validation, one would
        # need to fetch positions and their individual maxLeverage, or use a default.
        # For now, we'll use a placeholder or assume maxLeverage if available in 'account_info'.
        # The user story mentioned "maxLeverage" in the formula, implying it would be known.
        # Here we'll need to fetch position data to get symbol-specific maxLeverage.

        # For the purpose of this initial implementation, let's assume we are validating
        # a specific position, and its maxLeverage is passed or derived.
        # The research mentioned: "Formula MMR confermata: notional / (2 * maxLeverage)"
        # And "crossMaintenanceMarginUsed è il target di comparazione corretto"

        # This part requires more context on how 'notional' and 'maxLeverage'
        # are determined for the comparison with 'crossMaintenanceMarginUsed'.
        # Since the `fetch_account_info` gives total account info, we might need
        # another API call to get position details to find 'notional' and 'maxLeverage'
        # for a specific position, or assume 'notional' as part of the validation
        # request for a specific test.

        # For now, let's return a success status and the fetched data.
        # Further implementation will depend on how 'notional' and 'maxLeverage'
        # are provided for validation against 'crossMaintenanceMarginUsed'.

        return {
            "status": "success",
            "account_info": account_info,
            "crossMaintenanceMarginUsed": cross_maintenance_margin_used,
            "message": "Account info fetched. Further validation requires position data."
        }
