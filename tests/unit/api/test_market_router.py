"""Unit tests for market router."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from src.liquidationheatmap.api.main import app

client = TestClient(app)

class TestMarketRouter:
    def test_list_exchanges(self):
        response = client.get("/exchanges")
        assert response.status_code == 200
        data = response.json()
        assert "exchanges" in data
        assert any(e["name"].lower() == "binance" for e in data["exchanges"])

    def test_get_exchanges_health(self):
        response = client.get("/exchanges/health")
        assert response.status_code == 200
        data = response.json()
        assert "binance" in data
        assert data["binance"] == "healthy"

    def test_list_symbols(self):
        response = client.get("/symbols")
        assert response.status_code == 200
        data = response.json()
        assert "BTCUSDT" in data

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    def test_get_klines_success(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db._table_exists.return_value = True
        mock_db.conn.execute.return_value.df.return_value.to_dict.return_value = [{"open_time": "2024-01-01"}]
        
        response = client.get("/prices/klines?symbol=BTCUSDT&interval=5m&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert len(data["data"]) == 1

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    def test_get_klines_unsupported_interval(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db._table_exists.return_value = False
        
        response = client.get("/prices/klines?symbol=BTCUSDT&interval=99m")
        assert response.status_code == 400
        assert "Unsupported interval" in response.json()["detail"]

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    def test_get_data_date_range_success(self, mock_db_cls):
        from datetime import datetime
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db.conn.execute.return_value.fetchone.return_value = (datetime(2024, 1, 1), datetime(2024, 1, 2))
        
        response = client.get("/data/date-range?symbol=BTCUSDT")
        assert response.status_code == 200
        data = response.json()
        assert "start_date" in data
        assert "end_date" in data

    def test_get_data_date_range_invalid_symbol(self):
        response = client.get("/data/date-range?symbol=INVALID")
        assert response.status_code == 400

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    def test_get_data_date_range_no_data(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db.conn.execute.return_value.fetchone.return_value = (None, None)
        
        response = client.get("/data/date-range?symbol=BTCUSDT")
        assert response.status_code == 404
