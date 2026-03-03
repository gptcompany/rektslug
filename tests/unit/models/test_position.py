"""Unit tests for position models - LiquidationLevel, HeatmapCell, HeatmapSnapshot.

TDD RED phase: Write failing tests before implementation.
"""

from datetime import datetime
from decimal import Decimal

import pytest


class TestLiquidationLevel:
    """Tests for LiquidationLevel dataclass (T004)."""

    def test_liquidation_level_creation_long(self):
        """LiquidationLevel should be creatable with valid long position data."""
        from src.liquidationheatmap.models.position import LiquidationLevel

        level = LiquidationLevel(
            entry_price=Decimal("100000"),
            liq_price=Decimal("91000"),
            volume=Decimal("50000"),
            side="long",
            leverage=10,
            created_at=datetime(2025, 11, 15, 12, 0, 0),
        )

        assert level.entry_price == Decimal("100000")
        assert level.liq_price == Decimal("91000")
        assert level.volume == Decimal("50000")
        assert level.side == "long"
        assert level.leverage == 10
        assert level.is_active() is True
        assert level.consumed_at is None

    def test_liquidation_level_creation_short(self):
        """LiquidationLevel should be creatable with valid short position data."""
        from src.liquidationheatmap.models.position import LiquidationLevel

        level = LiquidationLevel(
            entry_price=Decimal("100000"),
            liq_price=Decimal("109000"),
            volume=Decimal("25000"),
            side="short",
            leverage=10,
            created_at=datetime(2025, 11, 15, 12, 0, 0),
        )

        assert level.side == "short"
        assert level.is_active() is True

    def test_liquidation_level_consumed(self):
        """LiquidationLevel should track consumption time."""
        from src.liquidationheatmap.models.position import LiquidationLevel

        level = LiquidationLevel(
            entry_price=Decimal("100000"),
            liq_price=Decimal("91000"),
            volume=Decimal("50000"),
            side="long",
            leverage=10,
            created_at=datetime(2025, 11, 15, 12, 0, 0),
            consumed_at=datetime(2025, 11, 16, 8, 0, 0),
        )

        assert level.is_active() is False
        assert level.consumed_at == datetime(2025, 11, 16, 8, 0, 0)

    def test_liquidation_level_invalid_leverage(self):
        """LiquidationLevel should reject invalid leverage values."""
        from src.liquidationheatmap.models.position import LiquidationLevel

        with pytest.raises(ValueError, match="Invalid leverage"):
            LiquidationLevel(
                entry_price=Decimal("100000"),
                liq_price=Decimal("91000"),
                volume=Decimal("50000"),
                side="long",
                leverage=15,  # Invalid - not in {5, 10, 25, 50, 100}
                created_at=datetime(2025, 11, 15, 12, 0, 0),
            )

    def test_liquidation_level_invalid_side(self):
        """LiquidationLevel should reject invalid side values."""
        from src.liquidationheatmap.models.position import LiquidationLevel

        with pytest.raises(ValueError, match="Invalid side"):
            LiquidationLevel(
                entry_price=Decimal("100000"),
                liq_price=Decimal("91000"),
                volume=Decimal("50000"),
                side="invalid",  # Invalid
                leverage=10,
                created_at=datetime(2025, 11, 15, 12, 0, 0),
            )

    def test_liquidation_level_invalid_volume(self):
        """LiquidationLevel should reject non-positive volume."""
        from src.liquidationheatmap.models.position import LiquidationLevel

        with pytest.raises(ValueError, match="Volume must be positive"):
            LiquidationLevel(
                entry_price=Decimal("100000"),
                liq_price=Decimal("91000"),
                volume=Decimal("0"),  # Invalid
                side="long",
                leverage=10,
                created_at=datetime(2025, 11, 15, 12, 0, 0),
            )


class TestHeatmapCell:
    """Tests for HeatmapCell dataclass (T005)."""

    def test_heatmap_cell_creation(self):
        """HeatmapCell should be creatable with price bucket."""
        from src.liquidationheatmap.models.position import HeatmapCell

        cell = HeatmapCell(price_bucket=Decimal("95000"))

        assert cell.price_bucket == Decimal("95000")
        assert cell.long_density == Decimal("0")
        assert cell.short_density == Decimal("0")

    def test_heatmap_cell_with_densities(self):
        """HeatmapCell should support custom densities."""
        from src.liquidationheatmap.models.position import HeatmapCell

        cell = HeatmapCell(
            price_bucket=Decimal("95000"),
            long_density=Decimal("1234567.89"),
            short_density=Decimal("987654.32"),
        )

        assert cell.long_density == Decimal("1234567.89")
        assert cell.short_density == Decimal("987654.32")

    def test_heatmap_cell_total_density(self):
        """HeatmapCell.total_density should sum long and short."""
        from src.liquidationheatmap.models.position import HeatmapCell

        cell = HeatmapCell(
            price_bucket=Decimal("95000"),
            long_density=Decimal("1000"),
            short_density=Decimal("500"),
        )

        assert cell.total_density == Decimal("1500")


class TestHeatmapSnapshot:
    """Tests for HeatmapSnapshot dataclass (T005)."""

    def test_heatmap_snapshot_creation(self):
        """HeatmapSnapshot should be creatable with timestamp and symbol."""
        from src.liquidationheatmap.models.position import HeatmapSnapshot

        snapshot = HeatmapSnapshot(
            timestamp=datetime(2025, 11, 15, 12, 0, 0),
            symbol="BTCUSDT",
        )

        assert snapshot.timestamp == datetime(2025, 11, 15, 12, 0, 0)
        assert snapshot.symbol == "BTCUSDT"
        assert len(snapshot.cells) == 0
        assert snapshot.total_long_volume == Decimal("0")
        assert snapshot.total_short_volume == Decimal("0")

    def test_heatmap_snapshot_get_cell_creates(self):
        """HeatmapSnapshot.get_cell should create cell if not exists."""
        from src.liquidationheatmap.models.position import HeatmapSnapshot

        snapshot = HeatmapSnapshot(
            timestamp=datetime(2025, 11, 15, 12, 0, 0),
            symbol="BTCUSDT",
        )

        cell = snapshot.get_cell(Decimal("95000"))

        assert cell.price_bucket == Decimal("95000")
        assert Decimal("95000") in snapshot.cells

    def test_heatmap_snapshot_get_cell_returns_existing(self):
        """HeatmapSnapshot.get_cell should return existing cell."""
        from src.liquidationheatmap.models.position import HeatmapCell, HeatmapSnapshot

        snapshot = HeatmapSnapshot(
            timestamp=datetime(2025, 11, 15, 12, 0, 0),
            symbol="BTCUSDT",
        )

        # Create cell manually
        snapshot.cells[Decimal("95000")] = HeatmapCell(
            price_bucket=Decimal("95000"),
            long_density=Decimal("1000"),
        )

        # Get should return same cell
        cell = snapshot.get_cell(Decimal("95000"))

        assert cell.long_density == Decimal("1000")

    def test_heatmap_snapshot_to_dict(self):
        """HeatmapSnapshot.to_dict should return API-compatible format."""
        from src.liquidationheatmap.models.position import HeatmapCell, HeatmapSnapshot

        snapshot = HeatmapSnapshot(
            timestamp=datetime(2025, 11, 15, 12, 0, 0),
            symbol="BTCUSDT",
            total_long_volume=Decimal("100000"),
            total_short_volume=Decimal("80000"),
            positions_created=10,
            positions_consumed=3,
        )

        snapshot.cells[Decimal("95000")] = HeatmapCell(
            price_bucket=Decimal("95000"),
            long_density=Decimal("50000"),
            short_density=Decimal("0"),
        )

        result = snapshot.to_dict()

        assert result["timestamp"] == "2025-11-15T12:00:00"
        assert result["symbol"] == "BTCUSDT"
        assert len(result["levels"]) == 1
        assert result["levels"][0]["price"] == 95000.0
        assert result["levels"][0]["long_density"] == 50000.0
        assert result["meta"]["total_long_volume"] == 100000.0
        assert result["meta"]["positions_created"] == 10


class TestCalculateLiqPrice:
    """Tests for calculate_liq_price function (T006)."""

    def test_long_liquidation_10x(self):
        """10x long position should liquidate ~9.6% below entry (with 0.4% MMR)."""
        from src.liquidationheatmap.models.position import calculate_liq_price

        # Entry: $100,000, Leverage: 10x, Side: long, MMR: 0.4%
        # Formula: entry * (1 - 1/10 + 0.004) = entry * (1 - 0.1 + 0.004) = entry * 0.904
        liq_price = calculate_liq_price(
            entry_price=Decimal("100000"),
            leverage=10,
            side="long",
        )

        expected = Decimal("100000") * Decimal("0.904")
        assert liq_price == expected

    def test_short_liquidation_10x(self):
        """10x short position should liquidate ~9.6% above entry (with 0.4% MMR)."""
        from src.liquidationheatmap.models.position import calculate_liq_price

        # Formula: entry * (1 + 1/10 - 0.004) = entry * (1 + 0.1 - 0.004) = entry * 1.096
        liq_price = calculate_liq_price(
            entry_price=Decimal("100000"),
            leverage=10,
            side="short",
        )

        expected = Decimal("100000") * Decimal("1.096")
        assert liq_price == expected

    def test_long_liquidation_100x(self):
        """100x long position should liquidate ~0.6% below entry."""
        from src.liquidationheatmap.models.position import calculate_liq_price

        # Formula: entry * (1 - 1/100 + 0.004) = entry * (1 - 0.01 + 0.004) = entry * 0.994
        liq_price = calculate_liq_price(
            entry_price=Decimal("100000"),
            leverage=100,
            side="long",
        )

        expected = Decimal("100000") * Decimal("0.994")
        assert liq_price == expected

    def test_short_liquidation_5x(self):
        """5x short position should liquidate ~19.6% above entry."""
        from src.liquidationheatmap.models.position import calculate_liq_price

        # Formula: entry * (1 + 1/5 - 0.004) = entry * (1 + 0.2 - 0.004) = entry * 1.196
        liq_price = calculate_liq_price(
            entry_price=Decimal("100000"),
            leverage=5,
            side="short",
        )

        expected = Decimal("100000") * Decimal("1.196")
        assert liq_price == expected

    def test_custom_mmr(self):
        """Should accept custom maintenance margin rate."""
        from src.liquidationheatmap.models.position import calculate_liq_price

        # With 1% MMR instead of 0.4%
        liq_price = calculate_liq_price(
            entry_price=Decimal("100000"),
            leverage=10,
            side="long",
            mmr=Decimal("0.01"),
        )

        # Formula: entry * (1 - 1/10 + 0.01) = entry * (1 - 0.1 + 0.01) = entry * 0.91
        expected = Decimal("100000") * Decimal("0.91")
        assert liq_price == expected
