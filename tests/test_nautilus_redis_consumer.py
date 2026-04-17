import pytest
import json
from src.liquidationheatmap.nautilus.redis_consumer import NautilusSignalConsumer
from src.liquidationheatmap.nautilus.data import LiquidationSignalData

def test_nautilus_consumer_processes_message():
    consumer = NautilusSignalConsumer()
    
    message_data = json.dumps({
        "symbol": "BTCUSDT",
        "price": "95000.50",
        "side": "long",
        "confidence": 0.85,
        "timestamp": "2026-04-17T12:00:00Z",
        "source": "liquidationheatmap",
        "signal_id": "sig123"
    })
    
    signal = consumer._process_message(message_data)
    
    assert isinstance(signal, LiquidationSignalData)
    assert signal.symbol == "BTCUSDT"
    assert signal.price == 95000.50
    assert signal.side == "long"
    assert signal.confidence == 0.85
    assert signal.signal_id == "sig123"
    assert signal.ts_event > 0
