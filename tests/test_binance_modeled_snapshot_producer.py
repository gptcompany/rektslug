import pytest
import json
import duckdb
import pandas as pd
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from src.liquidationheatmap.modeled_snapshots.snapshot_schema import validate_artifact
from src.liquidationheatmap.modeled_snapshots.binance_producer import BinanceProducer

@pytest.fixture
def mock_db(tmp_path):
    db_file = tmp_path / "test.db"
    conn = duckdb.connect(str(db_file))
    
    # Setup tables
    conn.execute("CREATE TABLE klines_1m_history (symbol VARCHAR, open_time TIMESTAMP, close DOUBLE)")
    conn.execute("CREATE TABLE open_interest_history (symbol VARCHAR, timestamp TIMESTAMP, open_interest_value DOUBLE)")
    conn.execute("""
        CREATE TABLE aggtrades_history (
            agg_trade_id BIGINT, 
            timestamp TIMESTAMP, 
            symbol VARCHAR, 
            exchange VARCHAR, 
            price DOUBLE, 
            quantity DOUBLE, 
            side VARCHAR, 
            gross_value DOUBLE
        )
    """)
    
    # Insert some data
    conn.execute("INSERT INTO klines_1m_history VALUES ('BTCUSDT', '2026-04-07 12:00:00', 50000.0)")
    conn.execute("INSERT INTO open_interest_history VALUES ('BTCUSDT', '2026-04-07 12:00:00', 10000.0)")
    conn.execute("INSERT INTO aggtrades_history VALUES (1, '2026-04-07 11:59:00', 'BTCUSDT', 'binance', 50000.0, 10.0, 'buy', 500000.0)")
    
    conn.close()
    return str(db_file)

def test_binance_producer_dual_channel_export(tmp_path, mock_db, monkeypatch):
    producer = BinanceProducer(base_dir=tmp_path, db_path=mock_db)
    snapshot_ts = "2026-04-07T12:00:00Z"
    
    # Mock _collect_orderbook to avoid needing a real Parquet file
    def mock_collect_orderbook(symbol, ts):
        orderbook = {
            'bids': [(49900.0, 1.0), (49800.0, 2.0)],
            'asks': [(50100.0, 1.0), (50200.0, 2.0)]
        }
        identity = {"source": "mock", "timestamp": ts, "status": "available"}
        return orderbook, identity, "available"
    
    monkeypatch.setattr(producer, "_collect_orderbook", mock_collect_orderbook)
    
    manifest = producer.export_snapshot(symbol="BTCUSDT", snapshot_ts=snapshot_ts)
    
    assert manifest.exchange == "binance"
    assert "binance_standard" in manifest.models
    assert "binance_depth_weighted" in manifest.models
    assert manifest.models["binance_standard"].availability_status == "available"
    assert manifest.models["binance_depth_weighted"].availability_status == "available"
    
    # Check artifact files
    for channel in ["binance_standard", "binance_depth_weighted"]:
        path = tmp_path / "artifacts" / "BTCUSDT" / snapshot_ts / f"{channel}.json"
        assert path.exists()
        with open(path, "r") as f:
            data = json.load(f)
        validate_artifact(data)

def test_binance_depth_weighted_impact(tmp_path, mock_db, monkeypatch):
    producer = BinanceProducer(base_dir=tmp_path, db_path=mock_db)
    snapshot_ts = "2026-04-07T12:00:00Z"
    
    # Test that different depths produce different results
    def mock_ob_low_depth(symbol, ts):
        # Very low depth at liquidation levels (approx 49200 for 50x)
        return {'bids': [(49500.0, 0.001)], 'asks': [(50500.0, 0.001)]}, {}, "available"
        
    def mock_ob_high_depth(symbol, ts):
        # Very high depth
        return {'bids': [(49500.0, 10000.0)], 'asks': [(50500.0, 10000.0)]}, {}, "available"

    # 1. Run with low depth
    monkeypatch.setattr(producer, "_collect_orderbook", mock_ob_low_depth)
    producer.export_snapshot(symbol="BTCUSDT", snapshot_ts=snapshot_ts, channels=["binance_depth_weighted"])
    with open(tmp_path / "artifacts" / "BTCUSDT" / snapshot_ts / "binance_depth_weighted.json", "r") as f:
        low_depth_data = json.load(f)
        
    # 2. Run with high depth
    monkeypatch.setattr(producer, "_collect_orderbook", mock_ob_high_depth)
    producer.export_snapshot(symbol="BTCUSDT", snapshot_ts=snapshot_ts, channels=["binance_depth_weighted"])
    with open(tmp_path / "artifacts" / "BTCUSDT" / snapshot_ts / "binance_depth_weighted.json", "r") as f:
        high_depth_data = json.load(f)
        
    # Verify volumes are different
    # Sum of volumes in long_distribution
    low_sum = sum(low_depth_data["long_distribution"].values())
    high_sum = sum(high_depth_data["long_distribution"].values())
    
    assert low_sum != high_sum
    assert low_sum > high_sum # Low depth should increase impact multiplier


def test_binance_partial_manifest_keeps_artifact_path_when_open_interest_missing(tmp_path):
    db_file = tmp_path / "partial.db"
    conn = duckdb.connect(str(db_file))
    conn.execute("CREATE TABLE klines_1m_history (symbol VARCHAR, open_time TIMESTAMP, close DOUBLE)")
    conn.execute("CREATE TABLE open_interest_history (symbol VARCHAR, timestamp TIMESTAMP, open_interest_value DOUBLE)")
    conn.execute("""
        CREATE TABLE aggtrades_history (
            agg_trade_id BIGINT,
            timestamp TIMESTAMP,
            symbol VARCHAR,
            exchange VARCHAR,
            price DOUBLE,
            quantity DOUBLE,
            side VARCHAR,
            gross_value DOUBLE
        )
    """)
    conn.execute("INSERT INTO klines_1m_history VALUES ('BTCUSDT', '2026-04-07 12:00:00', 50000.0)")
    conn.close()

    producer = BinanceProducer(base_dir=tmp_path, db_path=str(db_file))
    snapshot_ts = "2026-04-07T12:00:00Z"

    manifest = producer.export_snapshot(
        symbol="BTCUSDT", snapshot_ts=snapshot_ts, channels=["binance_standard"]
    )

    entry = manifest.models["binance_standard"]
    assert entry.availability_status == "partial"
    assert entry.artifact_path == f"artifacts/BTCUSDT/{snapshot_ts}/binance_standard.json"
    assert entry.source_metadata["availability_metadata"]["reason"] == "Input collection was partial"
    assert (tmp_path / "artifacts" / "BTCUSDT" / snapshot_ts / "binance_standard.json").exists()
