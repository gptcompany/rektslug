"""Unit tests for market router."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pandas as pd

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
        assert response.json()["binance"] == "healthy"

    def test_list_symbols(self):
        response = client.get("/symbols")
        assert response.status_code == 200
        assert "BTCUSDT" in response.json()

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.market.QuestDBService")
    def test_get_klines_prefers_questdb(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.get_recent_klines.return_value = [{"open_time": "2024-01-01T00:00:00+00:00"}]

        response = client.get("/prices/klines?symbol=BTCUSDT&interval=5m&limit=10")

        assert response.status_code == 200
        assert response.json()["data"] == [{"open_time": "2024-01-01T00:00:00+00:00"}]
        assert response.headers["X-Data-Backend"] == "questdb"
        mock_db_cls.assert_not_called()

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.market.QuestDBService")
    def test_get_klines_hot_intervals_do_not_fall_back_to_duckdb(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.get_recent_klines.return_value = []

        response = client.get("/prices/klines?symbol=BTCUSDT&interval=5m&limit=10")

        assert response.status_code == 404
        assert "No QuestDB kline data found" in response.json()["detail"]
        mock_db_cls.assert_not_called()

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.market.QuestDBService")
    def test_get_klines_non_hot_intervals_fall_back_to_duckdb(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.get_recent_klines.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db._table_exists.return_value = True
        mock_db.conn.execute.return_value.df.return_value.to_dict.return_value = [{"open_time": "2024-01-01"}]

        response = client.get("/prices/klines?symbol=BTCUSDT&interval=15m&limit=10")

        assert response.status_code == 200
        assert response.json()["data"] == [{"open_time": "2024-01-01"}]
        assert response.headers["X-Data-Backend"] == "duckdb"

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.market.QuestDBService")
    def test_get_klines_duckdb_serializes_timestamps(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.get_recent_klines.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db._table_exists.return_value = True
        mock_db.conn.execute.return_value.df.return_value.to_dict.return_value = [
            {"open_time": pd.Timestamp("2024-01-01T00:00:00Z")}
        ]

        response = client.get("/prices/klines?symbol=BTCUSDT&interval=15m&limit=10")

        assert response.status_code == 200
        assert response.json()["data"] == [{"open_time": "2024-01-01T00:00:00+00:00"}]
        assert response.headers["X-Data-Backend"] == "duckdb"

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.market.QuestDBService")
    def test_get_klines_unsupported_interval(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.get_recent_klines.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__.return_value = mock_db
        mock_db._table_exists.return_value = False

        response = client.get("/prices/klines?symbol=BTCUSDT&interval=99m")

        assert response.status_code == 400
        assert "Unsupported interval" in response.json()["detail"]

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.market.QuestDBService")
    def test_get_data_date_range_prefers_questdb(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.is_available.return_value = True
        mock_qdb_cls.return_value.get_open_interest_date_range.return_value = (
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
        )

        response = client.get("/data/date-range?symbol=BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["start_date"].startswith("2024-01-01")
        assert data["end_date"].startswith("2024-01-02")
        assert response.headers["X-Data-Backend"] == "questdb"
        mock_db_cls.assert_not_called()

    def test_get_data_date_range_invalid_symbol(self):
        response = client.get("/data/date-range?symbol=INVALID")
        assert response.status_code == 400

    @patch("src.liquidationheatmap.api.routers.market.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.market.QuestDBService")
    def test_get_data_date_range_no_data(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.is_available.return_value = True
        mock_qdb_cls.return_value.get_open_interest_date_range.return_value = None

        response = client.get("/data/date-range?symbol=BTCUSDT")

        assert response.status_code == 404
        assert "No data found in QuestDB" in response.json()["detail"]
        mock_db_cls.assert_not_called()

    @patch("src.liquidationheatmap.api.routers.market.QuestDBService")
    def test_get_data_date_range_returns_503_when_questdb_unavailable(self, mock_qdb_cls):
        mock_qdb_cls.return_value.is_available.return_value = False

        response = client.get("/data/date-range?symbol=BTCUSDT")

        assert response.status_code == 503
        assert "Retry-After" in response.headers
        assert response.json()["error"] == "Service Unavailable"
