"""Contract tests for the spec-022 CoinAnK public liq-map endpoint."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.api.routers import liquidations
from src.liquidationheatmap.ingestion.db_service import IngestionLockError


@pytest.fixture
def client():
    return TestClient(app)


def _sample_public_map_payload() -> dict:
    return {
        "schema_version": "1.0",
        "source": "coinank-public-builder",
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "profile": "rektslug-ank-public",
        "current_price": 60123.45,
        "grid": {
            "step": 10.0,
            "anchor_price": 60123.45,
            "min_price": 55200.0,
            "max_price": 64800.0,
        },
        "leverage_ladder": [
            "25x",
            "30x",
            "40x",
            "50x",
            "60x",
            "70x",
            "80x",
            "90x",
            "100x",
        ],
        "long_buckets": [
            {"price_level": 59800.0, "leverage": "50x", "volume": 1234567.89},
        ],
        "short_buckets": [
            {"price_level": 60500.0, "leverage": "50x", "volume": 987654.32},
        ],
        "cumulative_long": [
            {"price_level": 59800.0, "value": 1234567.89},
            {"price_level": 60123.45, "value": 0.0},
        ],
        "cumulative_short": [
            {"price_level": 60123.45, "value": 0.0},
            {"price_level": 60500.0, "value": 987654.32},
        ],
        "last_data_timestamp": datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc).isoformat(),
        "is_stale_real_data": False,
    }


class TestCoinankPublicMapContract:
    def test_endpoint_exists_and_returns_typed_schema(self, client, monkeypatch):
        monkeypatch.setattr(
            liquidations,
            "build_coinank_public_map_response",
            lambda **_kwargs: _sample_public_map_payload(),
        )

        response = client.get(
            "/liquidations/coinank-public-map",
            params={"symbol": "BTCUSDT", "timeframe": "1d"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["schema_version"] == "1.0"
        assert data["source"] == "coinank-public-builder"
        assert data["exchange"] == "binance"
        assert data["symbol"] == "BTCUSDT"
        assert data["timeframe"] == "1d"
        assert data["profile"] == "rektslug-ank-public"
        assert data["grid"]["step"] == 10.0
        assert data["leverage_ladder"] == [
            "25x",
            "30x",
            "40x",
            "50x",
            "60x",
            "70x",
            "80x",
            "90x",
            "100x",
        ]
        assert data["cumulative_long"][-1] == {
            "price_level": 60123.45,
            "value": 0.0,
        }
        assert data["cumulative_short"][0] == {
            "price_level": 60123.45,
            "value": 0.0,
        }

    def test_unsupported_symbol_is_rejected(self, client):
        response = client.get(
            "/liquidations/coinank-public-map",
            params={"symbol": "SOLUSDT", "timeframe": "1d"},
        )
        assert response.status_code == 400

    def test_unsupported_timeframe_is_rejected(self, client):
        response = client.get(
            "/liquidations/coinank-public-map",
            params={"symbol": "BTCUSDT", "timeframe": "30d"},
        )
        assert response.status_code == 400

    def test_builder_failure_returns_explicit_json_500(self, client, monkeypatch):
        def _boom(**_kwargs):
            raise RuntimeError("builder exploded")

        monkeypatch.setattr(liquidations, "build_coinank_public_map_response", _boom)

        response = client.get(
            "/liquidations/coinank-public-map",
            params={"symbol": "BTCUSDT", "timeframe": "1d"},
        )

        assert response.status_code == 500
        assert response.json() == {
            "error": "RuntimeError",
            "detail": "builder exploded",
        }

    def test_transient_duckdb_lock_is_retried(self, client, monkeypatch):
        attempts = {"count": 0}

        async def _fake_sleep(_delay):
            return None

        def _flaky(**_kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise IngestionLockError("Database locked by another DuckDB process. Retry shortly.")
            return _sample_public_map_payload()

        monkeypatch.setattr(liquidations.asyncio, "sleep", _fake_sleep)
        monkeypatch.setattr(liquidations, "build_coinank_public_map_response", _flaky)

        response = client.get(
            "/liquidations/coinank-public-map",
            params={"symbol": "BTCUSDT", "timeframe": "1d"},
        )

        assert response.status_code == 200
        assert attempts["count"] == 2

    def test_legacy_levels_endpoint_remains_available(self, client, monkeypatch):
        class _PriceResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"price":"60123.45"}'

        monkeypatch.setattr(liquidations, "urlopen", lambda *_args, **_kwargs: _PriceResponse())

        response = client.get(
            "/liquidations/levels",
            params={"symbol": "BTCUSDT", "model": "openinterest", "timeframe": 7},
        )

        assert response.status_code == 200
        data = response.json()
        assert "long_liquidations" in data
        assert "short_liquidations" in data
        assert "Sunset" not in response.headers
