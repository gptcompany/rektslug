"""Parity checks between the OI SQL model and the standard Python formula."""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.models.binance_standard import BinanceStandardModel

class TestOIModelParity:
    """Verify parity between SQL-based and Python-based liquidation formulas."""

    def test_sql_parity_with_binance_standard_model(self, tmp_path):
        db_path = tmp_path / "parity.duckdb"
        symbol = "BTCUSDT"
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0, tzinfo=None)
        
        # We'll use a single bin scenario
        with DuckDBService(str(db_path)) as db:
            db.conn.execute("CREATE TABLE open_interest_history (timestamp TIMESTAMP, symbol VARCHAR, open_interest_value DECIMAL(20,8))")
            db.conn.execute("CREATE TABLE klines_5m_history (open_time TIMESTAMP, symbol VARCHAR, open DECIMAL, high DECIMAL, low DECIMAL, close DECIMAL, volume DECIMAL, quote_volume DECIMAL)")
            
            # 150 candles to pass coverage check
            for i in range(151):
                t = now - timedelta(minutes=5 * (150 - i))
                db.conn.execute("INSERT INTO open_interest_history VALUES (?, ?, ?)", [t, symbol, 1000000000.0 + i * 1000000.0])
                # Bullish candle
                db.conn.execute("INSERT INTO klines_5m_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                                [t, symbol, 50000.0, 50100.0, 49900.0, 50050.0, 1000.0, 50000000.0])

            # Run SQL model
            df = db.calculate_liquidations_oi_based(
                symbol=symbol,
                current_price=50000.0,
                bin_size=100.0,
                lookback_days=1,
                leverage_weights={10: 1.0}, # Test 10x
                kline_interval="5m"
            )
            
            sql_liq_price = df.iloc[0]["liq_price"]
            
            # Run Python model
            py_model = BinanceStandardModel()
            # SQL uses fixed 0.004 (0.4%) MMR currently in its calculation CTE
            mmr = Decimal("0.004")
            entry_price = Decimal("50000.0") # Based on bin_size 100 and price 50050
            leverage = 10
            
            # Long formula: entry * (1 - 1/leverage + mmr)
            expected_py_liq = py_model._calculate_long_liquidation(entry_price, leverage, mmr)
            
            assert float(expected_py_liq) == pytest.approx(sql_liq_price), \
                f"SQL Liq Price {sql_liq_price} differs from Python Model {expected_py_liq}"
