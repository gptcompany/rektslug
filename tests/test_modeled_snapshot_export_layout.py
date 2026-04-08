import pytest
import json
from dataclasses import asdict
from pathlib import Path
from src.liquidationheatmap.modeled_snapshots.export_layout import (
    build_manifest,
    write_manifest,
    write_modeled_artifact,
    write_backfill_batch_record,
    ModeledSnapshotManifest,
)
from src.liquidationheatmap.modeled_snapshots import reader as snapshot_reader
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
    # {exchange}/artifacts/{symbol}/{snapshot_ts}/
    payload = {"dummy": "data"}
    artifact_path = write_modeled_artifact(
        tmp_path, "binance", "BTCUSDT", "2026-04-07T12:00:00Z", "binance_standard", payload
    )
    assert artifact_path == tmp_path / "binance" / "artifacts" / "BTCUSDT" / "2026-04-07T12:00:00Z" / "binance_standard.json"
    
    # {exchange}/manifests/{symbol}/
    manifest = build_manifest("binance", "2026-04-07T12:00:00Z", [], {})
    manifest_path = write_manifest(tmp_path, "binance", "BTCUSDT", manifest)
    assert manifest_path == tmp_path / "binance" / "manifests" / "BTCUSDT" / "2026-04-07T12:00:00Z.json"
    
    # {exchange}/batches/
    batch_path = write_backfill_batch_record(tmp_path, "binance", "batch1", {"test": "data"})
    assert batch_path == tmp_path / "binance" / "batches" / "batch1.json"

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


def test_reader_resolves_artifact_written_under_exchange_root(tmp_path):
    artifact = _artifact()
    write_modeled_artifact(
        tmp_path,
        artifact.exchange,
        artifact.symbol,
        artifact.snapshot_ts,
        artifact.model_id,
        asdict(artifact),
    )
    manifest = build_manifest(artifact.exchange, artifact.snapshot_ts, [artifact], {})
    write_manifest(tmp_path, artifact.exchange, artifact.symbol, manifest)

    latest_ts = snapshot_reader.get_latest_snapshot_ts(
        artifact.exchange, artifact.symbol, base_dir=tmp_path
    )
    loaded = snapshot_reader.load_artifact(
        artifact.exchange,
        artifact.symbol,
        artifact.snapshot_ts,
        artifact.model_id,
        base_dir=tmp_path,
    )

    assert latest_ts == artifact.snapshot_ts
    assert loaded is not None
    assert loaded["model_id"] == artifact.model_id


def test_reader_prefers_latest_available_snapshot_over_newer_blocked_manifest(tmp_path):
    older = _artifact()
    newer_ts = "2026-04-08T12:00:00Z"

    write_modeled_artifact(
        tmp_path,
        older.exchange,
        older.symbol,
        older.snapshot_ts,
        older.model_id,
        asdict(older),
    )
    write_manifest(
        tmp_path,
        older.exchange,
        older.symbol,
        build_manifest(older.exchange, older.snapshot_ts, [older], {}),
    )
    write_manifest(
        tmp_path,
        older.exchange,
        older.symbol,
        build_manifest(
            older.exchange,
            newer_ts,
            [],
            {"binance_standard": {"status": "blocked_source_missing", "reason": "missing"}},
        ),
    )

    latest_manifest_ts = snapshot_reader.get_latest_snapshot_ts(
        older.exchange, older.symbol, base_dir=tmp_path
    )
    latest_available_ts = snapshot_reader.get_latest_available_snapshot_ts(
        older.exchange, older.symbol, older.model_id, base_dir=tmp_path
    )

    assert latest_manifest_ts == newer_ts
    assert latest_available_ts == older.snapshot_ts
