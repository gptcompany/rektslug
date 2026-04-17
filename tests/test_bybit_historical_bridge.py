import pytest
from pathlib import Path
from src.liquidationheatmap.modeled_snapshots.bybit_historical_bridge import BybitHistoricalBridge

def test_resolve_raw_path(tmp_path):
    bridge = BybitHistoricalBridge(
        historical_root=tmp_path / "historical",
        normalized_root=tmp_path / "normalized"
    )
    
    path = bridge.resolve_raw_path("BTCUSDT", "2024-01-01", "klines")
    assert path == tmp_path / "historical" / "klines" / "linear" / "BTCUSDT" / "1m" / "BTCUSDT_1m_2024-01-01.json"
    
def test_read_and_write_normalized_klines(tmp_path):
    bridge = BybitHistoricalBridge(
        historical_root=tmp_path / "historical",
        normalized_root=tmp_path / "normalized"
    )
    
    raw_path = tmp_path / "historical" / "klines" / "linear" / "BTCUSDT" / "1m" / "BTCUSDT_1m_2024-01-01.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text('[[1704067200000, "40000.0", "40100.0", "39900.0", "40050.0", "1.5", "60000.0"]]')
    
    df = bridge.read_raw("klines", raw_path)
    assert not df.empty
    assert "close" in df.columns
    assert "timestamp" in df.columns
    
    normalized_path, meta = bridge.write_normalized(df, "klines", "BTCUSDT", "2024-01-01", str(raw_path))
    
    assert normalized_path.exists()
    assert meta["source_path"] == str(raw_path)
    assert meta["digest"] is not None
