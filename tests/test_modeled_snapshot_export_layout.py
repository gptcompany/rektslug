import pytest
import json
from pathlib import Path
from src.liquidationheatmap.modeled_snapshots.export_layout import (
    build_manifest,
    write_manifest,
    write_modeled_artifact,
    write_backfill_batch_record,
    ModeledSnapshotManifest,
)
from src.liquidationheatmap.modeled_snapshots.snapshot_schema import ModeledSnapshotArtifact, BucketGrid


def _artifact(model_id: str = "binance_standard") -> ModeledSnapshotArtifact:
    return ModeledSnapshotArtifact(
        exchange="binance",
        model_id=model_id,
        symbol="BTCUSDT",
        snapshot_ts="2026-04-07T12:00:00Z",
        reference_price=100000.0,
        bucket_grid=BucketGrid(price_levels=[99000.0, 100000.0, 101000.0]),
        long_distribution={"99000.0": 1.0},
        short_distribution={"101000.0": 2.0},
        source_metadata={"input_identity": {"source": "fixture"}},
        generation_metadata={
            "run_id": "test-run",
            "run_reason": "test",
            "run_ts": "2026-04-07T12:00:01Z",
            "producer_version": "test",
        },
    )

def test_export_layout_paths(tmp_path):
    # Test that writing an artifact creates the correct canonical path
    # artifacts/{symbol}/{snapshot_ts}/
    payload = {"dummy": "data"}
    artifact_path = write_modeled_artifact(
        tmp_path, "binance", "BTCUSDT", "2026-04-07T12:00:00Z", "binance_standard", payload
    )
    assert artifact_path == tmp_path / "artifacts" / "BTCUSDT" / "2026-04-07T12:00:00Z" / "binance_standard.json"
    
    # manifests/{symbol}/
    manifest = build_manifest("binance", "2026-04-07T12:00:00Z", [], {})
    manifest_path = write_manifest(tmp_path, "binance", "BTCUSDT", manifest)
    assert manifest_path == tmp_path / "manifests" / "BTCUSDT" / "2026-04-07T12:00:00Z.json"
    
    # batches/
    batch_path = write_backfill_batch_record(tmp_path, "batch1", {"test": "data"})
    assert batch_path == tmp_path / "batches" / "batch1.json"

def test_manifest_json_loadable(tmp_path):
    # The manifest should be loadable as standard JSON without needing python objects
    manifest = build_manifest("binance", "2026-04-07T12:00:00Z", [], {})
    manifest_path = write_manifest(tmp_path, "binance", "BTCUSDT", manifest)
    with open(manifest_path, "r") as f:
        data = json.load(f)
    assert data["snapshot_ts"] == "2026-04-07T12:00:00Z"
    assert data["exchange"] == "binance"


def test_partial_artifact_manifest_keeps_artifact_path():
    artifact = _artifact()

    manifest = build_manifest(
        "binance",
        "2026-04-07T12:00:00Z",
        [artifact],
        {"binance_standard": {"status": "partial", "reason": "missing_funding"}},
    )

    entry = manifest.models["binance_standard"]

    assert entry.availability_status == "partial"
    assert entry.artifact_path == (
        "artifacts/BTCUSDT/2026-04-07T12:00:00Z/binance_standard.json"
    )
    assert entry.source_metadata["input_identity"] == {"source": "fixture"}
    assert entry.source_metadata["availability_metadata"]["reason"] == "missing_funding"
