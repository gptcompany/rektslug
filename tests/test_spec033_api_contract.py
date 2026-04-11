import pytest
from fastapi.testclient import TestClient
from src.liquidationheatmap.api.main import app

client = TestClient(app)

def test_get_coinank_public_map_accepts_reference_provider():
    response = client.get("/liquidations/coinank-public-map?exchange=binance&symbol=BTCUSDT&timeframe=1d&reference_provider=coinank")
    assert response.status_code == 200

def test_get_coinank_public_map_rejects_unsupported_provider():
    response = client.get("/liquidations/coinank-public-map?exchange=binance&symbol=BTCUSDT&timeframe=1d&reference_provider=invalid")
    assert response.status_code == 422
