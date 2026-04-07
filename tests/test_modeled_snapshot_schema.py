import pytest
from src.liquidationheatmap.modeled_snapshots.snapshot_schema import (
    ModeledSnapshotArtifact,
    validate_artifact,
    validate_iso8601_z_timestamp,
    BucketGrid,
)

def test_validate_iso8601_z_timestamp():
    assert validate_iso8601_z_timestamp("ts", "2026-04-07T12:00:00Z") == "2026-04-07T12:00:00Z"
    with pytest.raises(ValueError):
        validate_iso8601_z_timestamp("ts", "2026-04-07 12:00:00")

def test_validate_artifact_missing_exchange():
    payload = {
        "model_id": "binance_standard",
        "symbol": "BTCUSDT",
        "snapshot_ts": "2026-04-07T12:00:00Z",
        "reference_price": 50000.0,
        "bucket_grid": {"min_price": 40000, "max_price": 60000, "step": 100},
        "long_distribution": {"50000.0": 1.5},
        "short_distribution": {"50000.0": 2.5},
        "source_metadata": {"input_identity": {}},
        "generation_metadata": {"run_ts": "2026-04-07T12:05:00Z", "run_id": "1", "run_reason": "test", "producer_version": "1.0"}
    }
    with pytest.raises(ValueError, match="Missing required field: exchange"):
        validate_artifact(payload)

def test_validate_artifact_success():
    payload = {
        "exchange": "binance",
        "model_id": "binance_standard",
        "symbol": "BTCUSDT",
        "snapshot_ts": "2026-04-07T12:00:00Z",
        "reference_price": 50000.0,
        "bucket_grid": {"min_price": 40000, "max_price": 60000, "step": 100},
        "long_distribution": {"50000.0": 1.5},
        "short_distribution": {"50000.0": 2.5},
        "source_metadata": {"input_identity": {}},
        "generation_metadata": {"run_ts": "2026-04-07T12:05:00Z", "run_id": "1", "run_reason": "test", "producer_version": "1.0"}
    }
    artifact = validate_artifact(payload)
    assert artifact.exchange == "binance"
    assert artifact.model_id == "binance_standard"
    assert not hasattr(artifact, "research_policy_tag")
