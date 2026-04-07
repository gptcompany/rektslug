import pytest
import json
import duckdb
from pathlib import Path
from src.liquidationheatmap.modeled_snapshots.bybit_producer import BybitProducer

def test_bybit_blocked_manifest_gap(tmp_path):
    producer = BybitProducer(base_dir=tmp_path)
    # Gap is 2025-08-21 to 2026-04-05
    gap_ts = "2025-12-01T12:00:00Z"
    
    manifest = producer.export_snapshot(symbol="BTCUSDT", snapshot_ts=gap_ts, channels=["depth_weighted"])
    
    assert manifest.exchange == "bybit"
    assert manifest.models["depth_weighted"].availability_status == "blocked_source_missing"
    
    # Check that NO artifact was written
    artifact_dir = tmp_path / "artifacts" / "BTCUSDT" / gap_ts
    assert not artifact_dir.exists()
    
    # Check that manifest was written
    manifest_path = tmp_path / "manifests" / "BTCUSDT" / f"{gap_ts}.json"
    assert manifest_path.exists()
    
    with open(manifest_path, "r") as f:
        data = json.load(f)
    assert data["models"]["depth_weighted"]["availability_status"] == "blocked_source_missing"

def test_bybit_export_available_mock(tmp_path, monkeypatch):
    # Mocking paths and DB to test successful export
    producer = BybitProducer(base_dir=tmp_path)
    snapshot_ts = "2026-04-07T12:00:00Z"
    
    from src.liquidationheatmap.modeled_snapshots.bybit_readiness import ReadinessReport
    def mock_check_readiness(symbol, ts, channel):
        return ReadinessReport("bybit", ts, channel, "available", {})
        
    def mock_collect_inputs(symbol, ts, lookback, channel):
        import pandas as pd
        from decimal import Decimal
        inputs = {
            "current_price": Decimal("50000.0"),
            "open_interest": Decimal("1000000.0"),
            "large_trades": pd.DataFrame(),
            "orderbook": {'bids': [(49500.0, 1.0)], 'asks': [(50500.0, 1.0)]}
        }
        return inputs, {"mock": True}, "available"
        
    monkeypatch.setattr(producer.readiness_gate, "check_readiness", mock_check_readiness)
    monkeypatch.setattr(producer, "_collect_inputs", mock_collect_inputs)
    
    manifest = producer.export_snapshot(symbol="BTCUSDT", snapshot_ts=snapshot_ts)
    assert manifest.models["bybit_standard"].availability_status == "available"
    assert (tmp_path / "artifacts" / "BTCUSDT" / snapshot_ts / "bybit_standard.json").exists()


def test_bybit_partial_manifest_keeps_artifact_path(tmp_path, monkeypatch):
    producer = BybitProducer(base_dir=tmp_path)
    snapshot_ts = "2026-04-07T12:00:00Z"

    from src.liquidationheatmap.modeled_snapshots.bybit_readiness import ReadinessReport

    def mock_check_readiness(symbol, ts, channel):
        return ReadinessReport("bybit", ts, channel, "available", {})

    def mock_collect_inputs(symbol, ts, lookback, channel):
        import pandas as pd
        from decimal import Decimal

        inputs = {
            "current_price": Decimal("50000.0"),
            "open_interest": Decimal("1000000.0"),
            "large_trades": pd.DataFrame(),
        }
        input_identity = {
            "current_price": {"source": "mock", "timestamp": ts},
            "open_interest": {"source": "mock", "timestamp": ts},
            "funding": {"source": "missing", "status": "missing"},
            "large_trades": {"source": "mock", "count": 0},
        }
        return inputs, input_identity, "partial"

    monkeypatch.setattr(producer.readiness_gate, "check_readiness", mock_check_readiness)
    monkeypatch.setattr(producer, "_collect_inputs", mock_collect_inputs)

    manifest = producer.export_snapshot(
        symbol="BTCUSDT", snapshot_ts=snapshot_ts, channels=["bybit_standard"]
    )

    entry = manifest.models["bybit_standard"]
    assert entry.availability_status == "partial"
    assert entry.artifact_path == f"artifacts/BTCUSDT/{snapshot_ts}/bybit_standard.json"
    assert entry.source_metadata["availability_metadata"]["reason"] == "Input collection was partial"
