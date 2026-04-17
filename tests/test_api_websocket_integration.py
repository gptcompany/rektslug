import pytest
from fastapi.testclient import TestClient
from src.liquidationheatmap.api.main import app

client = TestClient(app)

def test_websocket_heatmap():
    with client.websocket_connect("/ws/heatmap/BTCUSDT/1h") as websocket:
        websocket.send_text("ping")
        data = websocket.receive_json()
        assert data == {"type": "pong"}

def test_websocket_liqmap():
    with client.websocket_connect("/ws/liqmap/BTCUSDT/1d") as websocket:
        websocket.send_text("ping")
        data = websocket.receive_json()
        assert data == {"type": "pong"}

def test_websocket_invalid_symbol():
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/heatmap/INVALIDSYMBOL/1h") as websocket:
            pass

def test_websocket_invalid_interval():
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/heatmap/BTCUSDT/invalid") as websocket:
            pass
