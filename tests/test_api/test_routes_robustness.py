"""Robustness tests for API routes."""

import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from decimal import Decimal
import pandas as pd
from datetime import datetime, timezone, timedelta
import duckdb

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.api.shared import SUPPORTED_SYMBOLS
from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.settings import clear_settings_cache

# We use a mock connection that doesn't actually close when .close() is called
class MockConn:
    def __init__(self):
        self.real_conn = duckdb.connect(":memory:")
    def execute(self, *args, **kwargs):
        return self.real_conn.execute(*args, **kwargs)
    def close(self):
        pass # Do not close during tests
    def __getattr__(self, name):
        return getattr(self.real_conn, name)

_shared_mock_conn = MockConn()

@pytest.fixture(autouse=True)
def setup_test_env():
    """Setup environment for testing."""
    os.environ["HEATMAP_DB_PATH"] = ":memory:"
    os.environ["REKTSLUG_INTERNAL_TOKEN"] = "test-token"
    clear_settings_cache()
    DuckDBService.reset_singletons()
    
    # Initialize shared memory DB
    _shared_mock_conn.real_conn.execute("CREATE TABLE IF NOT EXISTS liquidation_snapshots (id BIGINT PRIMARY KEY, timestamp TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, price_bucket DOUBLE NOT NULL, side VARCHAR NOT NULL, active_volume DOUBLE NOT NULL, density INTEGER DEFAULT 1, model VARCHAR DEFAULT 'binance_standard')")
    _shared_mock_conn.real_conn.execute("CREATE TABLE IF NOT EXISTS open_interest_history (id BIGINT PRIMARY KEY, timestamp TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, open_interest_value DOUBLE NOT NULL, open_interest_contracts DOUBLE NOT NULL, source VARCHAR DEFAULT 'ccxt')")
    _shared_mock_conn.real_conn.execute("CREATE TABLE IF NOT EXISTS klines_15m_history (open_time TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE, quote_volume DOUBLE, PRIMARY KEY (open_time, symbol))")
    _shared_mock_conn.real_conn.execute("CREATE TABLE IF NOT EXISTS liquidation_history (id BIGINT PRIMARY KEY, timestamp TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, side VARCHAR NOT NULL, price DOUBLE NOT NULL, quantity DOUBLE NOT NULL, leverage INTEGER DEFAULT 10, model VARCHAR DEFAULT 'binance_standard', is_buyer_maker BOOLEAN)")
    
    # Force all DuckDBService instances to use our mock connection
    with patch("src.liquidationheatmap.ingestion.db_service.duckdb.connect", return_value=_shared_mock_conn):
        yield
    
    # Cleanup data
    _shared_mock_conn.real_conn.execute("DELETE FROM liquidation_snapshots")
    _shared_mock_conn.real_conn.execute("DELETE FROM open_interest_history")
    
    if "HEATMAP_DB_PATH" in os.environ: del os.environ["HEATMAP_DB_PATH"]
    if "REKTSLUG_INTERNAL_TOKEN" in os.environ: del os.environ["REKTSLUG_INTERNAL_TOKEN"]
    clear_settings_cache()
    DuckDBService.reset_singletons()

@pytest.fixture
def client():
    return TestClient(app)

class TestApiRobustness:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_heatmap_with_real_data(self, client):
        now = datetime.now().replace(microsecond=0)
        _shared_mock_conn.real_conn.execute("INSERT OR REPLACE INTO liquidation_snapshots (id, timestamp, symbol, price_bucket, side, active_volume) VALUES (1, ?, 'BTCUSDT', 50000.0, 'long', 1000.0)", [now])
        _shared_mock_conn.real_conn.execute("INSERT OR REPLACE INTO open_interest_history (id, timestamp, symbol, open_interest_value, open_interest_contracts) VALUES (1, ?, 'BTCUSDT', 1000000.0, 20.0)", [now])
        
        response = client.get("/liquidations/heatmap?symbol=BTCUSDT")
        assert response.status_code == 200
        data = response.json()
        assert len(data["longs"]) >= 1

    def test_klines_aggregation_real(self, client):
        now = datetime.now().replace(microsecond=0)
        for i in range(15):
            _shared_mock_conn.real_conn.execute("INSERT OR REPLACE INTO klines_15m_history VALUES (?, 'BTCUSDT', 50000.0, 51000.0, 49000.0, 50500.0, 10.0, 505000.0)", [now - timedelta(minutes=15*i)])
            
        response = client.get("/prices/klines?symbol=BTCUSDT&interval=15m&limit=10")
        assert response.status_code == 200
