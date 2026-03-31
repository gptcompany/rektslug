"""QuestDB-first router tests for liquidation history endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.api.routers.liquidations import _get_latest_oi_with_questdb
from src.liquidationheatmap.models.position import HeatmapSnapshot

client = TestClient(app)


class TestLiquidationHistoryQuestDB:
    @patch("src.liquidationheatmap.api.routers.liquidations.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.liquidations.QuestDBService")
    def test_history_prefers_questdb(self, mock_qdb_cls, mock_db_cls):
        mock_qdb_cls.return_value.is_available.return_value = True
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
        mock_qdb_cls.return_value.is_available.return_value = True
        mock_qdb_cls.return_value.get_recent_liquidations.return_value = []

        response = client.get("/liquidations/history?symbol=BTCUSDT&limit=5")

        assert response.status_code == 200
        assert response.json() == []
        mock_db_cls.assert_not_called()

    @patch("src.liquidationheatmap.api.routers.liquidations.QuestDBService")
    def test_history_returns_503_when_questdb_unavailable(self, mock_qdb_cls):
        mock_qdb_cls.return_value.is_available.return_value = False

        response = client.get("/liquidations/history?symbol=BTCUSDT&limit=5")

        assert response.status_code == 503
        assert "Retry-After" in response.headers


class TestLiquidationLatestQuestDB:
    @patch("src.liquidationheatmap.api.routers.liquidations.QuestDBService")
    def test_latest_oi_helper_uses_questdb_only_when_available(self, mock_qdb_cls):
        qdb = mock_qdb_cls.return_value
        qdb.is_available.return_value = True
        qdb.get_latest_open_interest.return_value = (50000.0, 1250000.0)

        current_price, open_interest = _get_latest_oi_with_questdb("BTCUSDT")

        assert current_price == 50000.0
        assert open_interest == Decimal("1250000.0")
        qdb.get_latest_price.assert_not_called()

    @patch("src.liquidationheatmap.api.routers.liquidations.QuestDBService")
    def test_latest_oi_helper_falls_back_without_duckdb(self, mock_qdb_cls):
        qdb = mock_qdb_cls.return_value
        qdb.is_available.return_value = True
        qdb.get_latest_open_interest.return_value = (None, None)
        qdb.get_latest_price.return_value = None

        current_price, open_interest = _get_latest_oi_with_questdb("BTCUSDT")

        assert current_price > 0
        assert open_interest > 0

    @patch("src.liquidationheatmap.api.routers.liquidations.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.liquidations._get_latest_oi_with_questdb")
    def test_heatmap_does_not_open_duckdb_for_latest_data(self, mock_latest_oi, mock_db_cls):
        mock_latest_oi.return_value = (50000.0, Decimal("1000000"))

        response = client.get("/liquidations/heatmap?symbol=BTCUSDT&model=openinterest")

        assert response.status_code == 200
        assert response.json()["current_price"] == 50000.0
        mock_db_cls.assert_not_called()

    @patch("src.liquidationheatmap.api.routers.liquidations.QuestDBService")
    def test_latest_oi_helper_raises_503_when_questdb_unavailable(self, mock_qdb_cls):
        qdb = mock_qdb_cls.return_value
        qdb.is_available.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            _get_latest_oi_with_questdb("BTCUSDT")

        assert exc_info.value.status_code == 503

    @patch("src.liquidationheatmap.api.routers.liquidations.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.liquidations._get_latest_oi_with_questdb")
    def test_compare_models_does_not_open_duckdb_for_latest_data(
        self, mock_latest_oi, mock_db_cls
    ):
        mock_latest_oi.return_value = (50000.0, Decimal("1000000"))

        response = client.get("/liquidations/compare-models?symbol=BTCUSDT")

        assert response.status_code == 200
        assert len(response.json()["models"]) == 3
        mock_db_cls.assert_not_called()

    @patch("src.liquidationheatmap.api.routers.liquidations.EnsembleModel")
    @patch("src.liquidationheatmap.api.routers.liquidations._get_latest_funding_with_questdb")
    @patch("src.liquidationheatmap.api.routers.liquidations._get_latest_oi_with_questdb")
    def test_heatmap_ensemble_uses_questdb_funding(
        self, mock_latest_oi, mock_latest_funding, mock_ensemble_cls
    ):
        mock_latest_oi.return_value = (50000.0, Decimal("1000000"))
        mock_latest_funding.return_value = Decimal("0.0002")
        mock_ensemble = mock_ensemble_cls.return_value
        mock_ensemble.calculate_liquidations.return_value = []

        response = client.get("/liquidations/heatmap?symbol=BTCUSDT&model=ensemble")

        assert response.status_code == 200
        mock_ensemble.calculate_liquidations.assert_called_once_with(
            50000.0,
            Decimal("1000000"),
            symbol="BTCUSDT",
            funding_rate=Decimal("0.0002"),
        )

    @patch("src.liquidationheatmap.api.routers.liquidations.EnsembleModel")
    @patch("src.liquidationheatmap.api.routers.liquidations.FundingAdjustedModel")
    @patch("src.liquidationheatmap.api.routers.liquidations.BinanceStandardModel")
    @patch("src.liquidationheatmap.api.routers.liquidations._get_latest_funding_with_questdb")
    @patch("src.liquidationheatmap.api.routers.liquidations._get_latest_oi_with_questdb")
    def test_compare_models_uses_questdb_funding_for_funding_sensitive_models(
        self,
        mock_latest_oi,
        mock_latest_funding,
        mock_standard_cls,
        mock_funding_cls,
        mock_ensemble_cls,
    ):
        mock_latest_oi.return_value = (50000.0, Decimal("1000000"))
        mock_latest_funding.return_value = Decimal("0.0003")
        mock_standard_cls.return_value.calculate_liquidations.return_value = []
        mock_funding = mock_funding_cls.return_value
        mock_funding.calculate_liquidations.return_value = []
        mock_ensemble = mock_ensemble_cls.return_value
        mock_ensemble.calculate_liquidations.return_value = []

        response = client.get("/liquidations/compare-models?symbol=BTCUSDT")

        assert response.status_code == 200
        mock_funding.calculate_liquidations.assert_called_once_with(
            50000.0,
            Decimal("1000000"),
            symbol="BTCUSDT",
            funding_rate=Decimal("0.0003"),
        )
        mock_ensemble.calculate_liquidations.assert_called_once_with(
            50000.0,
            Decimal("1000000"),
            symbol="BTCUSDT",
            funding_rate=Decimal("0.0003"),
        )


class TestHeatmapTimeseriesQuestDB:
    @staticmethod
    def _snapshot(ts: datetime) -> HeatmapSnapshot:
        snapshot = HeatmapSnapshot(timestamp=ts, symbol="BTCUSDT")
        cell = snapshot.get_cell(Decimal("50000"))
        cell.long_density = Decimal("100")
        snapshot.total_long_volume = Decimal("100")
        snapshot.positions_created = 1
        return snapshot

    @patch("src.liquidationheatmap.api.routers.liquidations.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.liquidations._load_heatmap_snapshots_from_questdb")
    def test_heatmap_timeseries_prefers_questdb_live_for_hot_window(
        self, mock_qdb_loader, mock_db_cls
    ):
        mock_qdb_loader.return_value = [
            self._snapshot(datetime.now(timezone.utc) - timedelta(minutes=15))
        ]

        response = client.get(
            "/liquidations/heatmap-timeseries",
            params={
                "symbol": "BTCUSDT",
                "interval": "15m",
                "start_time": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
                "price_bin_size": 100,
            },
        )

        assert response.status_code == 200
        assert response.headers["X-Heatmap-Source"] == "live"
        assert response.headers["X-Heatmap-Backend"] == "questdb-live"
        assert response.json()["meta"]["total_snapshots"] == 1
        mock_db_cls.assert_not_called()

    @patch("src.liquidationheatmap.api.routers.liquidations.DuckDBService")
    @patch("src.liquidationheatmap.api.routers.liquidations._load_heatmap_snapshots_from_questdb")
    def test_heatmap_timeseries_falls_back_to_duckdb_when_hot_questdb_unavailable(
        self, mock_qdb_loader, mock_db_cls
    ):
        mock_db = mock_db_cls.return_value.__enter__.return_value
        mock_db.get_heatmap_timeseries.return_value = []
        mock_qdb_loader.side_effect = HTTPException(status_code=503, detail="QuestDB unavailable")

        response = client.get(
            "/liquidations/heatmap-timeseries",
            params={
                "symbol": "BTCUSDT",
                "interval": "15m",
                "start_time": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
                "price_bin_size": 100,
            },
        )

        assert response.status_code == 200
        assert response.headers["X-Heatmap-Backend"] == "duckdb-live"
        assert response.json()["meta"]["total_snapshots"] == 0
        mock_db.get_heatmap_timeseries.assert_called_once()

    @patch("src.liquidationheatmap.api.routers.liquidations._load_heatmap_snapshots_from_questdb")
    @patch("src.liquidationheatmap.api.routers.liquidations.DuckDBService")
    def test_heatmap_timeseries_uses_duckdb_for_cold_window(self, mock_db_cls, mock_qdb_loader):
        mock_db = mock_db_cls.return_value.__enter__.return_value
        mock_db.get_heatmap_timeseries.return_value = []

        response = client.get(
            "/liquidations/heatmap-timeseries",
            params={
                "symbol": "BTCUSDT",
                "interval": "15m",
                "start_time": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
                "price_bin_size": 100,
            },
        )

        assert response.status_code == 200
        assert response.headers["X-Heatmap-Backend"] == "duckdb-live"
        assert response.json()["meta"]["total_snapshots"] == 0
        mock_db.get_heatmap_timeseries.assert_called_once()
        mock_qdb_loader.assert_not_called()
