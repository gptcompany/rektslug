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
