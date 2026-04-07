import pytest
import json
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

def test_bybit_blocked_manifest_missing_path(tmp_path, monkeypatch):
    producer = BybitProducer(base_dir=tmp_path)
    snapshot_ts = "2026-04-07T12:00:00Z"
    
    # Mock readiness to return missing for everything
    from src.liquidationheatmap.modeled_snapshots.bybit_readiness import ReadinessReport
    def mock_check_readiness(symbol, ts, channel):
        return ReadinessReport("bybit", ts, channel, "blocked_source_missing", {"all": {"present": False}})
        
    monkeypatch.setattr(producer.readiness_gate, "check_readiness", mock_check_readiness)
    
    manifest = producer.export_snapshot(symbol="BTCUSDT", snapshot_ts=snapshot_ts)
    assert manifest.models["bybit_standard"].availability_status == "blocked_source_missing"
