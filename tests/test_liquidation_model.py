"""
Tests for Binance liquidation calculation model.

Following TDD approach - tests written first, ONE at a time.
"""

import pytest

from src.models.liquidation import BinanceLiquidationModel


class TestBinanceLiquidationModel:
    """Test suite for Binance liquidation formula implementation."""

    def test_long_liquidation_10x_no_maintenance_margin(self):
        """
        Test long position liquidation at 10x leverage with zero maintenance margin.

        Formula: liq_price = entry_price * (1 - 1/leverage)
        Expected: 100 * (1 - 1/10) = 100 * 0.9 = 90.0
        """
        model = BinanceLiquidationModel()

        result = model.calculate_liquidation_price(
            entry_price=100.0, leverage=10, position_type="long", maintenance_margin_rate=0.0
        )

        assert result["liq_price"] == 90.0
        assert result["leverage"] == 10
        assert result["position_type"] == "long"

    def test_long_liquidation_5x_different_price(self):
        """
        Test long position at 5x leverage with different entry price.

        Formula: liq_price = entry_price * (1 - 1/leverage)
        Expected: 50000 * (1 - 1/5) = 50000 * 0.8 = 40000.0
        """
        model = BinanceLiquidationModel()

        result = model.calculate_liquidation_price(
            entry_price=50000.0, leverage=5, position_type="long", maintenance_margin_rate=0.0
        )

        assert result["liq_price"] == 40000.0
        assert result["leverage"] == 5

    def test_short_liquidation_10x_no_maintenance_margin(self):
        """
        Test short position liquidation at 10x leverage with zero maintenance margin.

        Formula: liq_price = entry_price * (1 + 1/leverage)
        Expected: 100 * (1 + 1/10) = 100 * 1.1 = 110.0
        """
        model = BinanceLiquidationModel()

        result = model.calculate_liquidation_price(
            entry_price=100.0, leverage=10, position_type="short", maintenance_margin_rate=0.0
        )

        assert result["liq_price"] == 110.0
        assert result["leverage"] == 10
        assert result["position_type"] == "short"

    def test_long_liquidation_10x_with_default_maintenance_margin(self):
        """Default 0.4% MMR must be added directly, not divided by leverage."""
        model = BinanceLiquidationModel()

        result = model.calculate_liquidation_price(
            entry_price=100.0, leverage=10, position_type="long"
        )

        assert result["liq_price"] == pytest.approx(90.4)
        assert result["distance_percent"] == pytest.approx(9.6)

    def test_short_liquidation_10x_with_default_maintenance_margin(self):
        """Default 0.4% MMR must be subtracted directly for shorts too."""
        model = BinanceLiquidationModel()

        result = model.calculate_liquidation_price(
            entry_price=100.0, leverage=10, position_type="short"
        )

        assert result["liq_price"] == pytest.approx(109.6)
        assert result["distance_percent"] == pytest.approx(9.6)

    def test_distance_percent_and_usd_calculation(self):
        """
        Test that distance_percent and distance_usd are calculated correctly.

        Formula:
        - distance_percent = abs((entry_price - liq_price) / entry_price) * 100
        - distance_usd = abs(entry_price - liq_price)

        Example (long 10x):
        - entry: 100, liq: 90
        - distance_percent = abs((100 - 90) / 100) * 100 = 10.0%
        - distance_usd = abs(100 - 90) = 10.0
        """
        model = BinanceLiquidationModel()

        result = model.calculate_liquidation_price(
            entry_price=100.0, leverage=10, position_type="long", maintenance_margin_rate=0.0
        )

        assert result["distance_percent"] == 10.0
        assert result["distance_usd"] == 10.0

    def test_risk_level_high_leverage(self):
        """Test that leverage >= 50x is classified as 'high' risk."""
        model = BinanceLiquidationModel()

        result = model.calculate_liquidation_price(
            entry_price=100.0, leverage=50, position_type="long"
        )

        assert result["risk_level"] == "high"

    def test_risk_level_medium_leverage(self):
        """Test that 25x <= leverage < 50x is classified as 'medium' risk."""
        model = BinanceLiquidationModel()

        result = model.calculate_liquidation_price(
            entry_price=100.0, leverage=25, position_type="long"
        )

        assert result["risk_level"] == "medium"

    def test_risk_level_low_leverage(self):
        """Test that leverage < 25x is classified as 'low' risk."""
        model = BinanceLiquidationModel()

        result = model.calculate_liquidation_price(
            entry_price=100.0, leverage=10, position_type="long"
        )

        assert result["risk_level"] == "low"

    def test_calculate_multiple_leverage_levels(self):
        """
        Test calculating liquidations for multiple leverage levels at once.

        This is the main method for API usage - returns dict with long_liquidations
        and short_liquidations lists.
        """
        model = BinanceLiquidationModel()

        results = model.calculate_liquidation_levels(
            entry_price=50000.0, leverage_levels=[5, 10, 25, 50, 100]
        )

        # Check structure
        assert "long_liquidations" in results
        assert "short_liquidations" in results

        # Check counts
        assert len(results["long_liquidations"]) == 5
        assert len(results["short_liquidations"]) == 5

        # Verify first long liquidation (5x)
        long_5x = results["long_liquidations"][0]
        assert long_5x["leverage"] == 5
        assert long_5x["position_type"] == "long"
        assert "liq_price" in long_5x
        assert "distance_percent" in long_5x
        assert "risk_level" in long_5x

        # Verify first short liquidation (5x)
        short_5x = results["short_liquidations"][0]
        assert short_5x["leverage"] == 5
        assert short_5x["position_type"] == "short"
