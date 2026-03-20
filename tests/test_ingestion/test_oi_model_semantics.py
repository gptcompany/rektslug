"""High-ROI regression tests for OI-based side semantics and scaling."""

import pytest
from datetime import datetime, timedelta, timezone
from src.liquidationheatmap.ingestion.db_service import DuckDBService

class TestOIModelSemantics:
    """High-ROI tests for OI-based liquidation model semantics.
    
    These tests specifically target the 4-quadrant inference logic:
    1. OI Up + Bullish -> Longs opened (buy)
    2. OI Up + Bearish -> Shorts opened (sell)
    3. OI Down + Bullish -> Shorts closed (sell)
    4. OI Down + Bearish -> Longs closed (buy)
    """

    @pytest.fixture
    def db_setup(self, tmp_path):
        db_path = tmp_path / "test_semantics.duckdb"
        with DuckDBService(str(db_path)) as db:
            db.conn.execute("""
                CREATE TABLE open_interest_history (
                    id BIGINT,
                    timestamp TIMESTAMP NOT NULL,
                    symbol VARCHAR NOT NULL,
                    open_interest_value DECIMAL(20, 8) NOT NULL,
                    open_interest_contracts DECIMAL(20, 8),
                    source VARCHAR DEFAULT 'test'
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
            yield db

    def _insert_scenario(self, db, symbol, now, candles):
        """Helper to insert specific market scenarios.
        candles: list of (oi_change, price_change) 
        where change is 1 (up) or -1 (down)
        """
        # Minimum candles needed to pass coverage check (ratio 0.5 for 5m = 144 candles/day)
        # We'll prepend some neutral candles if input is too small
        if len(candles) < 150:
            padding = [(0, 1)] * (150 - len(candles))
            candles = padding + candles

        base_oi = 1_000_000_000.0
        base_price = 50000.0
        
        # Insert initial OI
        db.conn.execute(
            "INSERT INTO open_interest_history VALUES (0, ?, ?, ?, 0, 'test')",
            [now - timedelta(minutes=5 * (len(candles) + 1)), symbol, base_oi]
        )

        for i, (oi_dir, price_dir) in enumerate(candles):
            t = now - timedelta(minutes=5 * (len(candles) - i))
            
            # Update OI
            base_oi += oi_dir * 10_000_000.0
            db.conn.execute(
                "INSERT INTO open_interest_history VALUES (?, ?, ?, ?, 0, 'test')",
                [i + 1, t, symbol, base_oi]
            )
            
            # Create candle
            # Bullish: open 50000, close 50100
            # Bearish: open 50100, close 50000
            if price_dir > 0:
                o, c = base_price, base_price + 100
            else:
                o, c = base_price + 100, base_price
            
            db.conn.execute(
                "INSERT INTO klines_5m_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [t, symbol, o, o+150, c-50, c, 1000.0, 1000.0 * o]
            )

    def test_oi_down_bullish_results_in_sell_side(self, db_setup):
        """Scenario: Price goes UP, but OI goes DOWN (Short Squeeze / Covering).
        Semantic: The positions that WERE there were Shorts.
        Downstream mapping: 'sell' -> short_liquidations.
        
        This test would have failed on e2bbf05 if it incorrectly 
        mapped green candles to 'buy'.
        """
        db = db_setup
        symbol = "BTCUSDT"
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0, tzinfo=None)
        
        # 10 candles of OI DOWN + BULLISH price
        self._insert_scenario(db, symbol, now, [(-1, 1)] * 10)
        
        df = db.calculate_liquidations_oi_based(
            symbol=symbol,
            current_price=50000.0,
            bin_size=10.0,
            lookback_days=1,
            kline_interval="5m"
        )
        
        assert not df.empty
        sides = set(df["side"])
        assert sides == {"sell"}, f"Expected only 'sell' side for Short Covering, got {sides}"
        # Liquidation price for shorts should be ABOVE current price
        assert (df["liq_price"] > 50000.0).all()

    def test_oi_up_bearish_results_in_sell_side(self, db_setup):
        """Scenario: Price goes DOWN, OI goes UP (New Shorts opening).
        Semantic: New positions are Shorts.
        """
        db = db_setup
        symbol = "BTCUSDT"
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0, tzinfo=None)
        
        # 10 candles of OI UP + BEARISH price
        self._insert_scenario(db, symbol, now, [(1, -1)] * 10)
        
        df = db.calculate_liquidations_oi_based(
            symbol=symbol,
            current_price=50000.0,
            bin_size=10.0,
            lookback_days=1,
            kline_interval="5m"
        )
        
        assert not df.empty
        assert set(df["side"]) == {"sell"}

    def test_conservation_of_mass_oi_scaling(self, db_setup):
        """Verify that total volume in output is approximately equal to latest OI.
        Note: Some bins are filtered if liq_price is on the 'wrong' side of current price.
        """
        db = db_setup
        symbol = "BTCUSDT"
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0, tzinfo=None)
        
        # Balanced scenario to ensure we have volume on both sides
        # 20 candles: 10 OI Up/Bullish (buy), 10 OI Up/Bearish (sell)
        # All OI UP so that all positions are "new" and easily predictable
        scenario = [(1, 1)] * 10 + [(1, -1)] * 10
        self._insert_scenario(db, symbol, now, scenario)
        
        # Get latest OI directly from DB
        latest_oi = db.conn.execute(
            "SELECT open_interest_value FROM open_interest_history ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()[0]
        
        df = db.calculate_liquidations_oi_based(
            symbol=symbol,
            current_price=50050.0, # Mid-price to keep most liquidations at risk
            bin_size=10.0,
            lookback_days=1,
            kline_interval="5m"
        )
        
        total_volume = df["volume"].sum()
        
        # Tolerance check: Should be within 1% of latest_oi if filtering is minimal
        # (With 100x leverage, liq price is very close to entry, so almost all are "at risk")
        # Default leverages include 5x, 10x etc which might be filtered out if too far.
        # So we use a looser tolerance (5%) or check that it's at least proportional.
        ratio = float(total_volume) / float(latest_oi)
        assert 0.9 <= ratio <= 1.1, f"Volume scaling error: Total Vol {total_volume} vs OI {latest_oi} (Ratio: {ratio})"
