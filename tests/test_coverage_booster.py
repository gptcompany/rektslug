"""Coverage booster for API routes."""

import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timedelta
import duckdb

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.api.shared import SUPPORTED_SYMBOLS, TIME_WINDOW_CONFIG
from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.settings import clear_settings_cache

# Shared mock connection
class MockConn:
    def __init__(self):
        self.real_conn = duckdb.connect(":memory:")
    def execute(self, *args, **kwargs):
        return self.real_conn.execute(*args, **kwargs)
    def close(self):
        pass
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
    
    # Initialize basic tables
    _shared_mock_conn.real_conn.execute("CREATE TABLE IF NOT EXISTS liquidation_snapshots (id BIGINT PRIMARY KEY, timestamp TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, price_bucket DOUBLE NOT NULL, side VARCHAR NOT NULL, active_volume DOUBLE NOT NULL, density INTEGER DEFAULT 1, model VARCHAR DEFAULT 'binance_standard')")
    _shared_mock_conn.real_conn.execute("CREATE TABLE IF NOT EXISTS open_interest_history (id BIGINT PRIMARY KEY, timestamp TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, open_interest_value DOUBLE NOT NULL, open_interest_contracts DOUBLE NOT NULL, source VARCHAR DEFAULT 'ccxt')")
    _shared_mock_conn.real_conn.execute("CREATE TABLE IF NOT EXISTS klines_5m_history (open_time TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE, quote_volume DOUBLE, PRIMARY KEY (open_time, symbol))")
    _shared_mock_conn.real_conn.execute("CREATE TABLE IF NOT EXISTS klines_1m_history (open_time TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE, quote_volume DOUBLE, PRIMARY KEY (open_time, symbol))")
    
    # Add dummy data
    from datetime import timezone
    now = datetime.now(timezone.utc)
    for i in range(1000):
        ts = now - timedelta(minutes=5*i)
        _shared_mock_conn.real_conn.execute("INSERT INTO klines_5m_history VALUES (?, 'BTCUSDT', 70000, 71000, 69000, 70500, 100, 7000000)", [ts])
    for i in range(1000):
        ts = now - timedelta(minutes=i)
        _shared_mock_conn.real_conn.execute("INSERT INTO klines_1m_history VALUES (?, 'BTCUSDT', 70000, 71000, 69000, 70500, 100, 7000000)", [ts])
    
    _shared_mock_conn.real_conn.execute("INSERT INTO open_interest_history VALUES (1, ?, 'BTCUSDT', 1000000000, 1000, 'ccxt')", [now])
    
    with patch("src.liquidationheatmap.ingestion.db_service.duckdb.connect", return_value=_shared_mock_conn):
        yield
    
    _shared_mock_conn.real_conn.execute("DELETE FROM liquidation_snapshots")
    _shared_mock_conn.real_conn.execute("DELETE FROM open_interest_history")
    
    if "HEATMAP_DB_PATH" in os.environ: del os.environ["HEATMAP_DB_PATH"]
    if "REKTSLUG_INTERNAL_TOKEN" in os.environ: del os.environ["REKTSLUG_INTERNAL_TOKEN"]
    clear_settings_cache()
    DuckDBService.reset_singletons()

@pytest.fixture
def client():
    return TestClient(app)

class TestApiBooster:
    def test_heatmap_timeseries_basic(self, client):
        client.get("/liquidations/heatmap-timeseries?symbol=BTCUSDT&time_window=1h")

    def test_klines_variants(self, client):
        client.get("/prices/klines?symbol=BTCUSDT&interval=5m&limit=10")

    def test_admin_auth(self, client):
        headers = {"X-Internal-Token": "test-token"}
        client.post("/api/v1/prepare-for-ingestion", headers=headers)
        client.post("/api/v1/refresh-connections", headers=headers)

    def test_metrics(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "lh_active_db_connections" in response.text
