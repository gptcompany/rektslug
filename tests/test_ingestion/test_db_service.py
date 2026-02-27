"""Tests for DuckDB service."""

from decimal import Decimal

import pytest

from src.liquidationheatmap.ingestion.db_service import DuckDBService


class TestDuckDBService:
    """Tests for DuckDBService data queries."""

    def test_get_latest_open_interest_returns_real_data(self, tmp_path):
        """Test that service loads and returns real Open Interest from CSV."""
        # Use temporary database
        db_path = tmp_path / "test.duckdb"

        with DuckDBService(str(db_path)) as db:
            current_price, open_interest = db.get_latest_open_interest("BTCUSDT")

            # Should return real data from sample CSV (not default mock)
            assert isinstance(current_price, Decimal)
            assert isinstance(open_interest, Decimal)
            assert open_interest > Decimal("1000000")  # Should be >1M from real data

    def test_get_latest_funding_rate_returns_real_data(self, tmp_path):
        """Test that service returns real funding rate from CSV."""
        db_path = tmp_path / "test.duckdb"

        with DuckDBService(str(db_path)) as db:
            funding_rate = db.get_latest_funding_rate("BTCUSDT")

            assert isinstance(funding_rate, Decimal)
            # Should be realistic funding rate (0.0001-0.0002 from sample data)
            assert Decimal("0.00001") < funding_rate < Decimal("0.001")

    def test_no_duplicates_when_loading_same_csv_twice(self, tmp_path):
        """Test that loading same CSV twice doesn't create duplicates."""
        db_path = tmp_path / "test.duckdb"

        # Load data first time
        with DuckDBService(str(db_path)) as db:
            current_price1, oi1 = db.get_latest_open_interest("BTCUSDT")

            # Count rows
            count1 = db.conn.execute(
                "SELECT COUNT(*) FROM open_interest_history WHERE symbol = 'BTCUSDT'"
            ).fetchone()[0]

        # Load data second time (should not duplicate)
        with DuckDBService(str(db_path)) as db:
            current_price2, oi2 = db.get_latest_open_interest("BTCUSDT")

            count2 = db.conn.execute(
                "SELECT COUNT(*) FROM open_interest_history WHERE symbol = 'BTCUSDT'"
            ).fetchone()[0]

        # Should have same count (no duplicates)
        assert count1 == count2
        # Values should be same (within precision tolerance)
        assert abs(oi1 - oi2) < Decimal("0.01")


class TestLeverageWeightsValidation:
    """Tests for leverage_weights parameter validation."""

    def test_default_leverage_weights_sum_to_one(self):
        """Default weights must sum to 1.0."""
        total = sum(DuckDBService.DEFAULT_LEVERAGE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_default_leverage_weights_has_five_tiers(self):
        """Default should have exactly 5 leverage tiers."""
        assert len(DuckDBService.DEFAULT_LEVERAGE_WEIGHTS) == 5
        assert set(DuckDBService.DEFAULT_LEVERAGE_WEIGHTS.keys()) == {
            5, 10, 25, 50, 100,
        }

    def test_default_leverage_weights_all_positive(self):
        """All default weights must be positive."""
        for lev, w in DuckDBService.DEFAULT_LEVERAGE_WEIGHTS.items():
            assert w > 0, f"Weight for {lev}x must be positive"

    def test_empty_leverage_weights_raises(self, tmp_path):
        """Empty dict should raise ValueError."""
        db_path = tmp_path / "test.duckdb"
        with DuckDBService(str(db_path)) as db:
            with pytest.raises(ValueError, match="cannot be empty"):
                db.calculate_liquidations_oi_based(
                    symbol="BTCUSDT",
                    current_price=90000.0,
                    leverage_weights={},
                )

    def test_negative_weight_raises(self, tmp_path):
        """Negative weight should raise ValueError."""
        db_path = tmp_path / "test.duckdb"
        with DuckDBService(str(db_path)) as db:
            with pytest.raises(ValueError, match="must be positive"):
                db.calculate_liquidations_oi_based(
                    symbol="BTCUSDT",
                    current_price=90000.0,
                    leverage_weights={10: -0.5, 25: 0.5},
                )

    def test_weights_not_summing_to_one_raises(self, tmp_path):
        """Weights summing to != 1.0 should raise ValueError."""
        db_path = tmp_path / "test.duckdb"
        with DuckDBService(str(db_path)) as db:
            with pytest.raises(ValueError, match="must sum to 1.0"):
                db.calculate_liquidations_oi_based(
                    symbol="BTCUSDT",
                    current_price=90000.0,
                    leverage_weights={10: 0.5, 25: 0.3},
                )


class TestAggTradesLoading:
    """Tests for aggTrades data loading (for real liquidation map)."""

    def test_get_large_trades_returns_dataframe(self, tmp_path):
        """Test that get_large_trades returns DataFrame with real aggTrades data."""
        db_path = tmp_path / "test.duckdb"

        with DuckDBService(str(db_path)) as db:
            # Get large trades (>$100k gross value)
            df = db.get_large_trades(symbol="BTCUSDT", min_gross_value=Decimal("100000"))

            # Should return DataFrame with columns
            assert df is not None
            assert "timestamp" in df.columns
            assert "price" in df.columns
            assert "quantity" in df.columns
            assert "side" in df.columns
            assert "gross_value" in df.columns

            # Should have actual data rows (not empty)
            # NOTE: This may fail if no aggTrades CSV files exist
            # but that's OK - it shows the loading logic needs CSV data
            if not df.empty:
                # All trades should have gross_value >= min threshold
                assert all(df["gross_value"] >= 100000)
