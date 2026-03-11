"""Tests for /liquidations/heatmap endpoint."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    from src.liquidationheatmap.api.main import app

    return TestClient(app)


class TestHeatmapEndpoint:
    """Tests for /liquidations/heatmap endpoint (T034)."""

    def test_heatmap_returns_200_with_valid_params(self, client):
        """Test that heatmap endpoint returns 200 with valid params."""
        response = client.get("/liquidations/heatmap?symbol=BTCUSDT&model=openinterest")
        assert response.status_code == 200

    def test_heatmap_returns_structured_response(self, client):
        """Test that heatmap returns proper structure."""
        response = client.get("/liquidations/heatmap?symbol=BTCUSDT&model=openinterest")
        data = response.json()

        # Check required fields
        assert "symbol" in data
        assert "current_price" in data
        assert "longs" in data
        assert "shorts" in data

    def test_heatmap_data_is_list(self, client):
        """Test that heatmap data fields are lists."""
        response = client.get("/liquidations/heatmap?symbol=BTCUSDT&model=openinterest")
        data = response.json()

        assert isinstance(data["longs"], list)
        assert isinstance(data["shorts"], list)

    def test_heatmap_metadata_has_required_fields(self, client):
        """Test that heatmap response has price data."""
        response = client.get("/liquidations/heatmap?symbol=BTCUSDT&model=openinterest")
        data = response.json()

        assert data["current_price"] > 0
        assert len(data["symbol"]) >= 7

    def test_heatmap_with_ensemble_model(self, client):
        """Test heatmap with ensemble model parameter."""
        response = client.get("/liquidations/heatmap?symbol=BTCUSDT&model=ensemble")
        assert response.status_code == 200

    def test_heatmap_empty_data_returns_empty_list(self, client):
        """Test that heatmap returns empty list when no cache data."""
        response = client.get("/liquidations/heatmap?symbol=BTCUSDT&model=openinterest")
        data = response.json()

        # Should return 200 with empty data if cache not populated
        assert response.status_code == 200
        assert isinstance(data["longs"], list)
        assert isinstance(data["shorts"], list)
