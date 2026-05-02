"""Contract tests for signal API endpoints.

TDD RED Phase: Tests written before implementation.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestSignalStatusEndpoint:
    """Contract tests for GET /signals/status."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        # Mock Redis and DB before importing app
        with patch("src.liquidationheatmap.api.routers.signals.get_redis_client") as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis_instance.is_connected = True
            raw_backend = MagicMock()
            raw_backend.get.return_value = "2026-04-17T12:00:00Z"
            raw_backend.zcount.return_value = 5
            mock_redis_instance.connect.return_value = raw_backend
            mock_redis.return_value = mock_redis_instance

            with patch("src.liquidationheatmap.api.routers.signals.FeedbackDBService") as mock_db:
                mock_db_instance = MagicMock()
                mock_db_instance.get_rolling_metrics.return_value = {
                    "total": 12,
                    "profitable": 9,
                    "hit_rate": 0.75,
                    "avg_pnl": 50.0,
                }
                mock_db.return_value = mock_db_instance

                # Import app after mocking
                from src.liquidationheatmap.api.main import app
                from src.liquidationheatmap.api.routers.signals import router

                # Register router if not already
                if not any(r.path == "/signals" for r in app.routes):
                    app.include_router(router)

                yield TestClient(app)

    def test_status_returns_200(self, client):
        """GET /signals/status should return 200."""
        response = client.get("/signals/status")
        assert response.status_code == 200

    def test_status_returns_connected(self, client):
        """Status should include connected boolean."""
        response = client.get("/signals/status")
        data = response.json()
        assert "connected" in data
        assert isinstance(data["connected"], bool)

    def test_status_returns_last_publish(self, client):
        """Status should include last_publish timestamp or null."""
        response = client.get("/signals/status")
        data = response.json()
        assert "last_publish" in data

    def test_status_returns_24h_counts(self, client):
        """Status should include 24h signal and feedback counts."""
        response = client.get("/signals/status")
        data = response.json()
        assert "signals_published_24h" in data
        assert "feedback_received_24h" in data
        assert isinstance(data["signals_published_24h"], int)
        assert isinstance(data["feedback_received_24h"], int)

    def test_status_uses_persisted_signal_count(self, client):
        """Status should use measured Redis-backed counts, not estimated values."""
        response = client.get("/signals/status")
        data = response.json()
        assert data["signals_published_24h"] == 5
        assert data["last_publish"].startswith("2026-04-17T12:00:00")

    def test_status_attempts_redis_connection_before_reporting_connected(self, client):
        """Status should not report degraded just because the singleton is still lazy."""
        with patch("src.liquidationheatmap.api.routers.signals.get_redis_client") as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis_instance.is_connected = True
            raw_backend = MagicMock()
            raw_backend.get.return_value = None
            raw_backend.zcount.return_value = 0
            mock_redis_instance.connect.return_value = raw_backend
            mock_redis.return_value = mock_redis_instance

            response = client.get("/signals/status")

        assert response.status_code == 200
        assert response.json()["connected"] is True
        mock_redis_instance.connect.assert_called()


class TestSignalMetricsEndpoint:
    """Contract tests for GET /signals/metrics."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        with patch("src.liquidationheatmap.api.routers.signals.get_redis_client") as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis_instance.is_connected = True
            mock_redis.return_value = mock_redis_instance

            with patch("src.liquidationheatmap.api.routers.signals.FeedbackDBService") as mock_db:
                mock_db_instance = MagicMock()
                mock_db_instance.get_rolling_metrics.return_value = {
                    "total": 100,
                    "profitable": 75,
                    "hit_rate": 0.75,
                    "avg_pnl": 50.0,
                }
                mock_db.return_value = mock_db_instance

                from src.liquidationheatmap.api.main import app
                from src.liquidationheatmap.api.routers.signals import router

                if not any(r.path == "/signals" for r in app.routes):
                    app.include_router(router)

                yield TestClient(app)

    def test_metrics_returns_200(self, client):
        """GET /signals/metrics should return 200."""
        response = client.get("/signals/metrics?symbol=BTCUSDT&window=24h")
        assert response.status_code == 200

    def test_metrics_returns_symbol(self, client):
        """Metrics should include requested symbol."""
        response = client.get("/signals/metrics?symbol=BTCUSDT&window=24h")
        data = response.json()
        assert data["symbol"] == "BTCUSDT"

    def test_metrics_returns_window(self, client):
        """Metrics should include requested window."""
        response = client.get("/signals/metrics?symbol=BTCUSDT&window=24h")
        data = response.json()
        assert data["window"] == "24h"

    def test_metrics_returns_hit_rate(self, client):
        """Metrics should include hit_rate between 0 and 1."""
        response = client.get("/signals/metrics?symbol=BTCUSDT&window=24h")
        data = response.json()
        assert "hit_rate" in data
        assert 0.0 <= data["hit_rate"] <= 1.0

    def test_metrics_returns_counts(self, client):
        """Metrics should include total_signals and feedback_count."""
        response = client.get("/signals/metrics?symbol=BTCUSDT&window=24h")
        data = response.json()
        assert "total_signals" in data
        assert "feedback_count" in data
        assert isinstance(data["total_signals"], int)
        assert isinstance(data["feedback_count"], int)

    def test_metrics_returns_avg_pnl(self, client):
        """Metrics should include avg_pnl."""
        response = client.get("/signals/metrics?symbol=BTCUSDT&window=24h")
        data = response.json()
        assert "avg_pnl" in data
        assert isinstance(data["avg_pnl"], (int, float))

    def test_metrics_supports_1h_window(self, client):
        """Should accept 1h window parameter."""
        response = client.get("/signals/metrics?symbol=BTCUSDT&window=1h")
        assert response.status_code == 200
        assert response.json()["window"] == "1h"

    def test_metrics_supports_7d_window(self, client):
        """Should accept 7d window parameter."""
        response = client.get("/signals/metrics?symbol=BTCUSDT&window=7d")
        assert response.status_code == 200
        assert response.json()["window"] == "7d"

    def test_metrics_default_symbol(self, client):
        """Should use BTCUSDT as default symbol."""
        response = client.get("/signals/metrics")
        assert response.status_code == 200
        assert response.json()["symbol"] == "BTCUSDT"


class TestSignalHealthEndpoint:
    """Contract tests for GET /signals/health."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        with patch("src.liquidationheatmap.api.routers.signals.get_redis_client") as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis_instance.is_connected = True
            mock_redis.return_value = mock_redis_instance

            from src.liquidationheatmap.api.main import app
            from src.liquidationheatmap.api.routers.signals import router

            if not any(r.path == "/signals" for r in app.routes):
                app.include_router(router)

            yield TestClient(app)

    def test_health_returns_200(self, client):
        """GET /signals/health should return 200."""
        response = client.get("/signals/health")
        assert response.status_code == 200

    def test_health_returns_status(self, client):
        """Health should include status field."""
        response = client.get("/signals/health")
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ok", "degraded"]

    def test_health_returns_redis_status(self, client):
        """Health should include redis_connected field."""
        response = client.get("/signals/health")
        data = response.json()
        assert "redis_connected" in data
        assert isinstance(data["redis_connected"], bool)
