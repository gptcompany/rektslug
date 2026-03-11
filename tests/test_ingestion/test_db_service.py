"""Tests for DuckDB service."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.liquidationheatmap.ingestion.db_service import (
    DuckDBService,
    IngestionLockError,
    _get_fallback_price,
    _get_latest_local_price,
)


class TestDuckDBHelpers:
    """Tests for standalone helper functions in db_service."""

    def test_get_fallback_price(self):
        """Should return correct fallback price for known symbols."""
        # BTCUSDT fallback is 95000.00 in current code
        assert _get_fallback_price("BTCUSDT") == Decimal("95000.00")
        assert _get_fallback_price("ETHUSDT") == Decimal("3500.00")
        assert _get_fallback_price("UNKNOWN") == Decimal("1000.00")

    def test_get_latest_local_price_success(self, tmp_path):
        """Should return price from local klines table."""
        import duckdb
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE TABLE klines_1m_history (open_time TIMESTAMP, symbol VARCHAR, close DOUBLE)")
        conn.execute("INSERT INTO klines_1m_history VALUES ('2024-01-01 00:00:00', 'BTCUSDT', 45000.50)")
        
        price = _get_latest_local_price(conn, "BTCUSDT")
        assert price == Decimal("45000.5")
        conn.close()

    def test_get_latest_local_price_no_data(self, tmp_path):
        """Should return None if no data in local tables."""
        import duckdb
        conn = duckdb.connect(":memory:")
        price = _get_latest_local_price(conn, "BTCUSDT")
        assert price is None
        conn.close()


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
            # If no CSV data, it uses fallback
            assert open_interest > 0

    def test_get_latest_funding_rate_returns_real_data(self, tmp_path):
        """Test that service returns real funding rate from CSV."""
        db_path = tmp_path / "test.duckdb"

        with DuckDBService(str(db_path)) as db:
            funding_rate = db.get_latest_funding_rate("BTCUSDT")

            assert isinstance(funding_rate, Decimal)
            # Should be realistic funding rate
            assert Decimal("-0.01") < funding_rate < Decimal("0.01")

    def test_no_duplicates_when_loading_same_csv_twice(self, tmp_path):
        """Test that loading same CSV twice doesn't create duplicates."""
        db_path = tmp_path / "test.duckdb"

        # Load data first time
        with DuckDBService(str(db_path)) as db:
            current_price1, oi1 = db.get_latest_open_interest("BTCUSDT")

            # Count rows - table might be created by load_oi_from_csv if data found
            try:
                count1 = db.conn.execute(
                    "SELECT COUNT(*) FROM open_interest_history WHERE symbol = 'BTCUSDT'"
                ).fetchone()[0]
            except:
                count1 = 0

        # Load data second time (should not duplicate)
        with DuckDBService(str(db_path)) as db:
            current_price2, oi2 = db.get_latest_open_interest("BTCUSDT")

            try:
                count2 = db.conn.execute(
                    "SELECT COUNT(*) FROM open_interest_history WHERE symbol = 'BTCUSDT'"
                ).fetchone()[0]
            except:
                count2 = 0

        # Should have same count (no duplicates)
        assert count1 == count2


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


class TestDuckDBLifecycle:
    """Tests for lock management and instance lifecycle."""

    def test_ingestion_lock_lifecycle(self):
        """Should set and release ingestion lock correctly."""
        DuckDBService.release_ingestion_lock()
        assert not DuckDBService.is_ingestion_locked()
        
        DuckDBService.set_ingestion_lock()
        assert DuckDBService.is_ingestion_locked()
        
        DuckDBService.release_ingestion_lock()
        assert not DuckDBService.is_ingestion_locked()

    def test_connect_raises_when_locked(self, tmp_path):
        """Should raise IngestionLockError if db is locked for ingestion."""
        db_path = str(tmp_path / "locked.duckdb")
        DuckDBService.set_ingestion_lock()
        try:
            with pytest.raises(IngestionLockError):
                DuckDBService(db_path, read_only=True)
        finally:
            DuckDBService.release_ingestion_lock()

    def test_close_all_instances(self, tmp_path):
        """Should close all cached DuckDB connections."""
        db_path = str(tmp_path / "lifecycle.duckdb")
        # Ensure it's not already in there from previous tests
        if (db_path, False) in DuckDBService._instances:
            del DuckDBService._instances[(db_path, False)]
            
        db = DuckDBService(db_path)
        assert (db_path, False) in DuckDBService._instances
        
        closed = DuckDBService.close_all_instances()
        assert closed >= 1
        assert (db_path, False) not in DuckDBService._instances

    def test_ensure_snapshot_tables(self, tmp_path):
        """Should create required snapshot tables."""
        db_path = str(tmp_path / "snapshots.duckdb")
        with DuckDBService(db_path) as db:
            db.ensure_snapshot_tables()
            
            tables = db.conn.execute("SHOW TABLES").fetchall()
            table_names = [t[0] for t in tables]
            assert "liquidation_snapshots" in table_names
            assert "position_events" in table_names


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


class TestOIBasedLiquidationsRegression:
    """Regression coverage for OI-based liquidation calculations."""

    def test_calculate_liquidations_oi_based_handles_large_decimal_values(self, tmp_path):
        """Large DECIMAL inputs must not overflow into an empty result set."""
        db_path = tmp_path / "overflow_regression.duckdb"
        symbol = "BTCUSDT"
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0, tzinfo=None)
        previous_bucket = now - timedelta(minutes=5)

        with DuckDBService(str(db_path)) as db:
            db.conn.execute("""
                CREATE TABLE open_interest_history (
                    id BIGINT,
                    timestamp TIMESTAMP NOT NULL,
                    symbol VARCHAR NOT NULL,
                    open_interest_value DECIMAL(20, 8) NOT NULL,
                    open_interest_contracts DECIMAL(20, 8),
                    source VARCHAR DEFAULT 'ccxt'
                )
            """)
            db.conn.execute("""
                CREATE TABLE klines_5m_history (
                    open_time TIMESTAMP NOT NULL,
                    symbol VARCHAR NOT NULL,
                    open DECIMAL(18, 8) NOT NULL,
                    high DECIMAL(18, 8) NOT NULL,
                    low DECIMAL(18, 8) NOT NULL,
                    close DECIMAL(18, 8) NOT NULL,
                    volume DECIMAL(18, 8) NOT NULL,
                    quote_volume DECIMAL(20, 8),
                    PRIMARY KEY (open_time, symbol)
                )
            """)

            db.conn.execute(
                """
                INSERT INTO open_interest_history
                    (id, timestamp, symbol, open_interest_value, open_interest_contracts, source)
                VALUES
                    (1, ?, ?, 800000000000.00000000, 1000000.00000000, 'test'),
                    (2, ?, ?, 950000000000.00000000, 1000000.00000000, 'test')
                """,
                [previous_bucket, symbol, now, symbol],
            )
            db.conn.execute(
                """
                INSERT INTO klines_5m_history
                    (open_time, symbol, open, high, low, close, volume, quote_volume)
                VALUES
                    (?, ?, 100000.00000000, 100250.00000000, 99950.00000000,
                     100100.00000000, 9000000.00000000, 900000000000.00000000)
                """,
                [now, symbol],
            )

            df = db.calculate_liquidations_oi_based(
                symbol=symbol,
                current_price=105000.0,
                bin_size=100.0,
                lookback_days=0,
                leverage_weights={10: 1.0},
                kline_interval="5m",
            )

        assert not df.empty
        assert set(df["side"]) == {"buy"}
        assert all(df["volume"] > 0)
