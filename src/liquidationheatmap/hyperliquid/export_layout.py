"""Export layout and manifest logic for Hyperliquid expert snapshots."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.liquidationheatmap.hyperliquid.snapshot_schema import ExpertSnapshotArtifact


@dataclass
class ManifestExpertEntry:
    expert_id: str
    availability_status: str
    research_policy_tag: str
    source_metadata: dict[str, Any]
    artifact_path: str | None = None


@dataclass
class ExpertSnapshotManifest:
    snapshot_ts: str
    experts: dict[str, ManifestExpertEntry]


def build_manifest(
    snapshot_ts: str,
    experts: list[ExpertSnapshotArtifact] | None = None,
    failures: dict[str, dict[str, Any]] | None = None,
) -> ExpertSnapshotManifest:
    experts = experts or []
    failures = failures or {}

    expert_dict = {e.expert_id: e for e in experts}

    manifest_entries = {}

    # All 5 expert channels MUST be present
    all_expert_ids = ["v1", "v2", "v3", "v4", "v5"]
    policy_tags = {
        "v1": "canonical",
        "v2": "shadow/control",
        "v3": "experimental",
        "v4": "experimental",
        "v5": "experimental",
    }

    for eid in all_expert_ids:
        if eid in expert_dict:
            # We have the expert artifact
            artifact = expert_dict[eid]
            manifest_entries[eid] = ManifestExpertEntry(
                expert_id=eid,
                availability_status="available",
                research_policy_tag=artifact.research_policy_tag,
                source_metadata=artifact.source_metadata,
                artifact_path=f"artifacts/{artifact.symbol}/{snapshot_ts}/{eid}.json",
            )
        elif eid in failures:
            manifest_entries[eid] = ManifestExpertEntry(
                expert_id=eid,
                availability_status="failed_decode",
                research_policy_tag=policy_tags[eid],
                source_metadata=failures[eid],
            )
        else:
            manifest_entries[eid] = ManifestExpertEntry(
                expert_id=eid,
                availability_status="missing",
                research_policy_tag=policy_tags[eid],
                source_metadata={"reason": "not_built"},
            )

    return ExpertSnapshotManifest(snapshot_ts=snapshot_ts, experts=manifest_entries)


def write_manifest(base_dir: Path | str, symbol: str, manifest: ExpertSnapshotManifest) -> Path:
    base_dir = Path(base_dir)
    manifest_dir = base_dir / "manifests" / symbol
    manifest_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = manifest_dir / f"{manifest.snapshot_ts}.json"

    # Convert manifest to dictionary that does not require internal schema types to load
    # (Consumer uses json.load)
    payload = {
        "snapshot_ts": manifest.snapshot_ts,
        "experts": {eid: asdict(entry) for eid, entry in manifest.experts.items()},
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return manifest_path


def write_expert_artifact(
    base_dir: Path | str, symbol: str, snapshot_ts: str, expert_id: str, payload: dict[str, Any]
) -> Path:
    """Write an expert artifact to the stable timestamp-derived layout."""
    base_dir = Path(base_dir)
    artifact_dir = base_dir / "artifacts" / symbol / snapshot_ts
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = artifact_dir / f"{expert_id}.json"

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
