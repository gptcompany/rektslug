"""
Binance liquidation price calculation model.

Implements Binance futures liquidation formula with maintenance margin.
"""


class BinanceLiquidationModel:
    """Calculate liquidation prices for Binance futures positions."""

    def calculate_liquidation_price(
        self, entry_price, leverage, position_type, maintenance_margin_rate=0.004
    ):
        """
        Calculate liquidation price using Binance formula.

        Formula:
        - Long:  liq_price = entry_price * (1 - 1/leverage + mmr)
        - Short: liq_price = entry_price * (1 + 1/leverage - mmr)

        This helper accepts a single maintenance margin rate. Tier selection is
        handled by higher-level models such as BinanceStandardModel.

        Args:
            entry_price: Entry price of the position
            leverage: Leverage multiplier (e.g., 10 for 10x)
            position_type: "long" or "short"
            maintenance_margin_rate: Maintenance margin rate (default 0.004 = 0.4%)

        Returns:
            Dictionary with liquidation details
        """
        # Calculate liquidation price based on position type
        if position_type == "long":
            liq_price = entry_price * (1 - 1 / leverage + maintenance_margin_rate)
        elif position_type == "short":
            liq_price = entry_price * (1 + 1 / leverage - maintenance_margin_rate)
        else:
            raise ValueError(f"position_type must be 'long' or 'short', got: {position_type}")

        # Round to 2 decimal places for clean API responses
        liq_price = round(liq_price, 2)

        # Calculate distance from entry price
        distance_usd = round(abs(entry_price - liq_price), 2)
        distance_percent = round((distance_usd / entry_price) * 100, 2)

        # Classify risk level based on leverage
        if leverage >= 50:
            risk_level = "high"
        elif leverage >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "liq_price": liq_price,
            "leverage": leverage,
            "position_type": position_type,
            "distance_percent": distance_percent,
            "distance_usd": distance_usd,
            "risk_level": risk_level,
        }

    def calculate_liquidation_levels(
        self,
        entry_price: float,
        leverage_levels: list[int] = None,
        maintenance_margin_rate: float = 0.004,
    ) -> dict:
        """
        Calculate liquidation levels for multiple leverages.

        Args:
            entry_price: Current or entry price
            leverage_levels: List of leverage multipliers (default: [5, 10, 25, 50, 100, 125])
            maintenance_margin_rate: Maintenance margin rate (default 0.004 = 0.4%)

        Returns:
            Dictionary with long_liquidations and short_liquidations lists
        """
        if leverage_levels is None:
            leverage_levels = [5, 10, 25, 50, 100, 125]

        long_liquidations = []
        short_liquidations = []

        for leverage in leverage_levels:
            # Calculate long liquidation
            long_liq = self.calculate_liquidation_price(
                entry_price=entry_price,
                leverage=leverage,
                position_type="long",
                maintenance_margin_rate=maintenance_margin_rate,
            )
            long_liquidations.append(long_liq)

            # Calculate short liquidation
            short_liq = self.calculate_liquidation_price(
                entry_price=entry_price,
                leverage=leverage,
                position_type="short",
                maintenance_margin_rate=maintenance_margin_rate,
            )
            short_liquidations.append(short_liq)

        return {"long_liquidations": long_liquidations, "short_liquidations": short_liquidations}
