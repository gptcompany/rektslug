"""QuestDB-first router tests for liquidation history endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.liquidationheatmap.api.main import app

client = TestClient(app)


class TestLiquidationHistoryQuestDB:
    @patch("src.liquidationheatmap.api.routers.liquidations.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.liquidations.QuestDBService")
    def test_history_prefers_questdb(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.get_recent_liquidations.return_value = [
            {
                "timestamp": "2026-03-26T12:05:00+00:00",
                "symbol": "BTCUSDT",
                "side": "long",
                "price": 50000.0,
                "quantity": 1.25,
                "leverage": 25.0,
            }
        ]

        response = client.get("/liquidations/history?symbol=BTCUSDT&limit=5")

        assert response.status_code == 200
        assert response.json()[0]["price"] == 50000.0
        mock_db_cls.assert_not_called()

    @patch("src.liquidationheatmap.api.routers.liquidations.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.liquidations.QuestDBService")
    def test_history_returns_empty_list_when_questdb_has_no_events(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.get_recent_liquidations.return_value = []

        response = client.get("/liquidations/history?symbol=BTCUSDT&limit=5")

        assert response.status_code == 200
        assert response.json() == []
        mock_db_cls.assert_not_called()
