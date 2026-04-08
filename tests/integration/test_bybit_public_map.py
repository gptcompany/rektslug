import pytest
from fastapi.testclient import TestClient
from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.modeled_snapshots import reader as snapshot_reader

@pytest.fixture
def client():
    return TestClient(app)

def test_bybit_public_map_uses_artifact(client):
    """Test that Bybit request picks up the artifact from Phase 2."""
    # Ensure there is an artifact for Bybit BTCUSDT 1w
    latest_ts = snapshot_reader.get_latest_snapshot_ts("bybit", "BTCUSDT")
    assert latest_ts is not None, "No Bybit BTCUSDT artifact found in data/validation/modeled_snapshots/"
    
    response = client.get("/liquidations/coinank-public-map", params={
        "exchange": "bybit",
        "symbol": "BTCUSDT",
        "timeframe": "1w"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["exchange"] == "bybit"
    assert data["symbol"] == "BTCUSDT"
    assert "modeled-snapshot-bybit_standard" in data["source"]
    assert len(data["long_buckets"]) > 0
    assert len(data["short_buckets"]) > 0
    # Verify leverage spreading
    assert data["leverage_ladder"] == [
        "25x", "30x", "40x", "50x", "60x", "70x", "80x", "90x", "100x"
    ]
    # Check if a bucket has 9 entries (one per tier)
    price_levels = set(b["price_level"] for b in data["long_buckets"])
    first_price = sorted(list(price_levels))[0]
    buckets_at_price = [b for b in data["long_buckets"] if b["price_level"] == first_price]
    assert len(buckets_at_price) == 9

def test_binance_public_map_legacy_regression(client):
    """Test that Binance request still works (regression for legacy path)."""
    response = client.get("/liquidations/coinank-public-map", params={
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1w"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["exchange"] == "binance"
    assert data["symbol"] == "BTCUSDT"
    # It might use artifact if available, or fall back to DuckDB
    assert data["source"] in ("coinank-public-builder", "modeled-snapshot-binance_standard")
    assert len(data["long_buckets"]) > 0


def test_hyperliquid_not_supported_on_unified_public_map(client):
    response = client.get("/liquidations/coinank-public-map", params={
        "exchange": "hyperliquid",
        "symbol": "BTCUSDT",
        "timeframe": "1w"
    })

    assert response.status_code == 400
    assert "Supported exchanges" in response.json()["detail"]
