import json
import shutil
import tempfile
from pathlib import Path

import pytest

from src.liquidationheatmap.hyperliquid.export_layout import (
    build_manifest,
    write_backfill_batch_record,
    write_expert_artifact,
    write_manifest,
)


@pytest.fixture
def temp_export_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)


def test_manifest_lists_all_five_experts():
    manifest = build_manifest(snapshot_ts="2026-04-03T12:00:00Z", experts=[])
    assert "v1" in manifest.experts
    assert "v2" in manifest.experts
    assert "v3" in manifest.experts
    assert "v4" in manifest.experts
    assert "v5" in manifest.experts


def test_missing_experts_have_availability_status():
    manifest = build_manifest(snapshot_ts="2026-04-03T12:00:00Z", experts=[])
    for expert_id, entry in manifest.experts.items():
        assert entry.availability_status in ["missing", "not_built", "failed_decode", "available"]


def test_source_decode_failures_are_machine_readable():
    manifest = build_manifest(
        snapshot_ts="2026-04-03T12:00:00Z",
        experts=[],
        failures={"v2": {"reason": "corrupt cache file"}},
    )
    assert manifest.experts["v2"].availability_status == "failed_decode"
    assert manifest.experts["v2"].source_metadata["reason"] == "corrupt cache file"


def test_manifest_can_be_parsed_with_json_load(temp_export_dir):
    manifest = build_manifest(snapshot_ts="2026-04-03T12:00:00Z", experts=[])

    symbol = "BTCUSDT"
    write_manifest(temp_export_dir, symbol, manifest)

    manifest_path = temp_export_dir / "manifests" / symbol / "2026-04-03T12:00:00Z.json"
    assert manifest_path.exists()

    with open(manifest_path, "r") as f:
        data = json.load(f)

    assert "snapshot_ts" in data
    assert "experts" in data
    assert "v1" in data["experts"]


def test_timestamp_derived_paths_use_canonical_format(temp_export_dir):
    # Pass artifact
    artifact_path = write_expert_artifact(
        temp_export_dir,
        symbol="BTCUSDT",
        snapshot_ts="2026-04-03T12:00:00Z",
        expert_id="v1",
        payload={"dummy": "data"},
    )
    expected_path = temp_export_dir / "artifacts" / "BTCUSDT" / "2026-04-03T12:00:00Z" / "v1.json"
    assert artifact_path == expected_path
    assert expected_path.exists()

    # Backfill batch
    batch_path = write_backfill_batch_record(
        temp_export_dir, batch_id="batch_1", payload={"interval": "1d"}
    )
    expected_batch_path = temp_export_dir / "batches" / "batch_1.json"
    assert batch_path == expected_batch_path
    assert expected_batch_path.exists()
