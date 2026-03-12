"""Binance Standard liquidation model with official MMR tiers."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List

from .base import AbstractLiquidationModel, LiquidationLevel


class BinanceStandardModel(AbstractLiquidationModel):
    """Calculate liquidations using official Binance formula with MMR tiers.

    Formula:
        Long:  liq_price = entry * (1 - 1/leverage + mmr)
        Short: liq_price = entry * (1 + 1/leverage - mmr)

    MMR (Maintenance Margin Rate) varies by position size.
    """

    # BTC/USDT MMR tiers (source: Binance official docs)
    MMR_TIERS = [
        (Decimal("50000"), Decimal("0.004"), Decimal("0")),  # 0-50k: 0.4%
        (Decimal("250000"), Decimal("0.005"), Decimal("50")),  # 50k-250k: 0.5%
        (Decimal("1000000"), Decimal("0.01"), Decimal("1300")),  # 250k-1M: 1.0%
        (Decimal("10000000"), Decimal("0.025"), Decimal("16300")),  # 1M-10M: 2.5%
        (Decimal("20000000"), Decimal("0.05"), Decimal("266300")),  # 10M-20M: 5.0%
        (Decimal("50000000"), Decimal("0.10"), Decimal("1266300")),  # 20M-50M: 10.0%
        (Decimal("100000000"), Decimal("0.125"), Decimal("2516300")),  # 50M-100M: 12.5%
        (Decimal("200000000"), Decimal("0.15"), Decimal("5016300")),  # 100M-200M: 15.0%
        (Decimal("300000000"), Decimal("0.25"), Decimal("25016300")),  # 200M-300M: 25.0%
        (Decimal("500000000"), Decimal("0.50"), Decimal("100016300")),  # 300M-500M: 50.0%
    ]

    @property
    def model_name(self) -> str:
        """Model identifier."""
        return "binance_standard"

    def calculate_liquidations(
        self,
        current_price: Decimal,
        open_interest: Decimal,
        symbol: str = "BTCUSDT",
        leverage_tiers: List[int] = None,
        num_bins: int = 50,
        large_trades=None,  # Optional DataFrame with real aggTrades data
    ) -> List[LiquidationLevel]:
        """Calculate liquidation levels using REAL trade data or synthetic binning.

        Args:
            current_price: Current market price
            open_interest: Total Open Interest in USDT
            symbol: Trading pair (default: BTCUSDT)
            leverage_tiers: List of leverage values (default: [5, 10, 25, 50, 100])
            num_bins: Number of bins per leverage tier (for synthetic mode)
            large_trades: Optional DataFrame with real aggTrades (timestamp, price, quantity, side, gross_value)

        Returns:
            List of LiquidationLevel objects
        """
        if leverage_tiers is None:
            leverage_tiers = [5, 10, 25, 50, 100]

        if current_price <= 0 or open_interest <= 0:
            raise ValueError("Price and Open Interest must be positive")

        liquidations = []
        timestamp = datetime.now()
        mmr = self._get_mmr(open_interest)
        logger = logging.getLogger(__name__)
        logger.info(
            f"BinanceStandardModel: current_price={current_price}, OI={open_interest}, large_trades={'None' if large_trades is None else len(large_trades)}"
        )

        # MODE 1: Use REAL trade data if provided (asymmetric, market-driven)
        if large_trades is not None and not large_trades.empty:
            logger.info(
                f"MODE 1: Processing {len(large_trades)} real trades (buy: {len(large_trades[large_trades['side'] == 'buy'])}, sell: {len(large_trades[large_trades['side'] == 'sell'])})"
            )
            for _, trade in large_trades.iterrows():
                entry_price = Decimal(str(trade["price"]))
                trade_volume = Decimal(str(trade["gross_value"]))
                side = trade["side"].lower()

                # For each leverage tier, calculate liquidation
                for leverage in leverage_tiers:
                    if side == "buy":  # Long entry → liquidation BELOW current price
                        liq_price = self._calculate_long_liquidation(entry_price, leverage, mmr)
                        if liq_price < current_price:  # Only include if below current price
                            liquidations.append(
                                LiquidationLevel(
                                    timestamp=timestamp,
                                    symbol=symbol,
                                    price_level=liq_price,
                                    liquidation_volume=trade_volume
                                    / len(leverage_tiers),  # Split across leverages
                                    leverage_tier=f"{leverage}x",
                                    side="long",
                                    confidence=self.confidence_score(),
                                )
                            )
                    elif side == "sell":  # Short entry → liquidation ABOVE current price
                        liq_price = self._calculate_short_liquidation(entry_price, leverage, mmr)
                        if liq_price > current_price:  # Only include if above current price
                            liquidations.append(
                                LiquidationLevel(
                                    timestamp=timestamp,
                                    symbol=symbol,
                                    price_level=liq_price,
                                    liquidation_volume=trade_volume / len(leverage_tiers),
                                    leverage_tier=f"{leverage}x",
                                    side="short",
                                    confidence=self.confidence_score(),
                                )
                            )

            logger.info(
                f"MODE 1 complete: {len(liquidations)} liquidations "
                f"(long: {len([liq for liq in liquidations if liq.side == 'long'])}, "
                f"short: {len([liq for liq in liquidations if liq.side == 'short'])})"
            )
            return liquidations

        # MODE 2: Fallback to synthetic Gaussian binning (symmetric, for testing)
        logger.info("MODE 2: Fallback to synthetic Gaussian binning")
        import numpy as np

        for leverage in leverage_tiers:
            # Volume per leverage tier
            volume_per_tier = open_interest / len(leverage_tiers) / 2  # Split long/short
            long_factor = Decimal("1") - Decimal("1") / Decimal(str(leverage)) + mmr
            short_factor = Decimal("1") + Decimal("1") / Decimal(str(leverage)) - mmr

            current_price_float = float(current_price)
            long_boundary = current_price_float / float(long_factor)
            if long_factor < Decimal("1"):
                long_start = current_price_float * 1.01
                long_end = min(current_price_float * 1.15, long_boundary * 0.99)
            else:
                long_start = long_boundary * 0.85
                long_end = long_boundary * 0.99
            if long_end <= long_start:
                long_start = long_boundary * 0.80
                long_end = long_boundary * 0.95
            entry_range_long = np.linspace(long_start, long_end, num_bins)

            # Gaussian distribution for realistic volume clustering
            entry_weights_long = np.exp(
                -0.5
                * ((entry_range_long - entry_range_long.mean()) / max(current_price_float * 0.03, 1.0))
                ** 2
            )
            entry_weights_long = entry_weights_long / entry_weights_long.sum()

            for entry_price, weight in zip(entry_range_long, entry_weights_long):
                liq_price = self._calculate_long_liquidation(
                    Decimal(str(entry_price)), leverage, mmr
                )
                liquidations.append(
                    LiquidationLevel(
                        timestamp=timestamp,
                        symbol=symbol,
                        price_level=liq_price,
                        liquidation_volume=volume_per_tier * Decimal(str(weight)),
                        leverage_tier=f"{leverage}x",
                        side="long",
                        confidence=self.confidence_score(),
                    )
                )

            short_boundary = current_price_float / float(short_factor)
            if short_factor > Decimal("1"):
                short_start = short_boundary * 1.01
                short_end = min(current_price_float * 0.99, short_boundary * 1.15)
            else:
                short_start = short_boundary * 1.01
                short_end = short_boundary * 1.15
            if short_end <= short_start:
                short_start = short_boundary * 1.02
                short_end = short_boundary * 1.20
            entry_range_short = np.linspace(short_start, short_end, num_bins)

            # Gaussian distribution
            entry_weights_short = np.exp(
                -0.5
                * ((entry_range_short - entry_range_short.mean()) / max(current_price_float * 0.03, 1.0))
                ** 2
            )
            entry_weights_short = entry_weights_short / entry_weights_short.sum()

            for entry_price, weight in zip(entry_range_short, entry_weights_short):
                liq_price = self._calculate_short_liquidation(
                    Decimal(str(entry_price)), leverage, mmr
                )
                liquidations.append(
                    LiquidationLevel(
                        timestamp=timestamp,
                        symbol=symbol,
                        price_level=liq_price,
                        liquidation_volume=volume_per_tier * Decimal(str(weight)),
                        leverage_tier=f"{leverage}x",
                        side="short",
                        confidence=self.confidence_score(),
                    )
                )

        return liquidations

    def confidence_score(self) -> Decimal:
        """Return confidence score for this model.

        Binance formula is most accurate (based on actual exchange behavior).
        """
        return Decimal("0.95")

    def _get_mmr(self, position_notional: Decimal) -> Decimal:
        """Get Maintenance Margin Rate based on position size.

        Args:
            position_notional: Position size in USDT

        Returns:
            MMR percentage (e.g., 0.004 for 0.4%)
        """
        for tier_max, mmr_rate, _ in self.MMR_TIERS:
            if position_notional <= tier_max:
                return mmr_rate

        # If exceeds all tiers, use highest tier
        return self.MMR_TIERS[-1][1]

    def _calculate_long_liquidation(
        self, entry_price: Decimal, leverage: int, mmr: Decimal
    ) -> Decimal:
        """Calculate long position liquidation price.

        Formula: entry * (1 - 1/leverage + mmr)
        """
        leverage_dec = Decimal(str(leverage))
        return entry_price * (Decimal("1") - Decimal("1") / leverage_dec + mmr)

    def _calculate_short_liquidation(
        self, entry_price: Decimal, leverage: int, mmr: Decimal
    ) -> Decimal:
        """Calculate short position liquidation price.

        Formula: entry * (1 + 1/leverage - mmr)
        """
        leverage_dec = Decimal(str(leverage))
        return entry_price * (Decimal("1") + Decimal("1") / leverage_dec - mmr)
