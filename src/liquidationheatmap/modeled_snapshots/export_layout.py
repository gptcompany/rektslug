"""Export layout and manifest logic for modeled snapshots."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.liquidationheatmap.modeled_snapshots.snapshot_schema import (
    ModeledSnapshotArtifact,
    validate_iso8601_z_timestamp,
)

VALID_AVAILABILITY_STATUSES = {
    "available",
    "partial",
    "blocked_source_unverified",
    "blocked_source_missing",
    "failed_processing",
    "unsupported",
}

@dataclass
class ManifestModelEntry:
    model_id: str
    availability_status: str
    source_metadata: dict[str, Any]
    artifact_path: str | None = None

    def __post_init__(self):
        if self.availability_status not in VALID_AVAILABILITY_STATUSES:
            raise ValueError(f"Invalid availability_status: {self.availability_status}")

@dataclass
class ModeledSnapshotManifest:
    exchange: str
    snapshot_ts: str
    distribution_normalization: str
    models: dict[str, ManifestModelEntry]

def build_manifest(
    exchange: str,
    snapshot_ts: str,
    artifacts: list[ModeledSnapshotArtifact] | None = None,
    failures: dict[str, dict[str, Any]] | None = None,
    distribution_normalization: str = "normalized",
) -> ModeledSnapshotManifest:
    snapshot_ts = validate_iso8601_z_timestamp("snapshot_ts", snapshot_ts)
    artifacts = artifacts or []
    failures = failures or {}

    manifest_entries = {}

    # Add available artifacts
    for artifact in artifacts:
        manifest_entries[artifact.model_id] = ManifestModelEntry(
            model_id=artifact.model_id,
            availability_status="available",
            source_metadata=artifact.source_metadata,
            artifact_path=f"artifacts/{artifact.symbol}/{snapshot_ts}/{artifact.model_id}.json",
        )

    # Add failures
    for model_id, failure_info in failures.items():
        status = failure_info.get("status", "failed_processing")
        if status not in VALID_AVAILABILITY_STATUSES:
            status = "failed_processing"
            
        manifest_entries[model_id] = ManifestModelEntry(
            model_id=model_id,
            availability_status=status,
            source_metadata=failure_info,
        )

    return ModeledSnapshotManifest(
        exchange=exchange,
        snapshot_ts=snapshot_ts,
        distribution_normalization=distribution_normalization,
        models=manifest_entries,
    )

def write_manifest(base_dir: Path | str, exchange: str, symbol: str, manifest: ModeledSnapshotManifest) -> Path:
    base_dir = Path(base_dir)
    manifest_dir = base_dir / "manifests" / symbol
    manifest_dir.mkdir(parents=True, exist_ok=True)

    snapshot_ts = validate_iso8601_z_timestamp("snapshot_ts", manifest.snapshot_ts)
    manifest_path = manifest_dir / f"{snapshot_ts}.json"

    # Convert manifest to dictionary that does not require internal schema types to load
    # (Consumer uses json.load)
    payload = {
        "exchange": manifest.exchange,
        "snapshot_ts": snapshot_ts,
        "distribution_normalization": manifest.distribution_normalization,
        "models": {mid: asdict(entry) for mid, entry in manifest.models.items()},
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return manifest_path

def write_modeled_artifact(
    base_dir: Path | str, exchange: str, symbol: str, snapshot_ts: str, model_id: str, payload: dict[str, Any]
) -> Path:
    """Write a modeled artifact to the stable timestamp-derived layout."""
    base_dir = Path(base_dir)
    snapshot_ts = validate_iso8601_z_timestamp("snapshot_ts", snapshot_ts)
    artifact_dir = base_dir / "artifacts" / symbol / snapshot_ts
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = artifact_dir / f"{model_id}.json"

    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return artifact_path

def write_backfill_batch_record(
    base_dir: Path | str, batch_id: str, payload: dict[str, Any]
) -> Path:
    """Write a backfill batch coverage summary."""
    base_dir = Path(base_dir)
    batch_dir = base_dir / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)

    batch_path = batch_dir / f"{batch_id}.json"

    with open(batch_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return batch_path
