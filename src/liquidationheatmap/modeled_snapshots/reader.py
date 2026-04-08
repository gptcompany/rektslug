"""Reader logic for modeled snapshot artifacts."""

import json
from pathlib import Path
from typing import Any

DEFAULT_MODELED_SNAPSHOT_ROOT = Path("data/validation/modeled_snapshots")

def list_available_snapshots(
    exchange: str,
    symbol: str,
    base_dir: Path | str = DEFAULT_MODELED_SNAPSHOT_ROOT,
) -> list[str]:
    """List all available snapshot timestamps for a given exchange and symbol."""
    base_dir = Path(base_dir)
    manifest_dir = base_dir / exchange / "manifests" / symbol.upper()
    if not manifest_dir.exists():
        return []
    
    # Manifests are named as {snapshot_ts}.json
    return sorted([p.stem for p in manifest_dir.glob("*.json")], reverse=True)

def get_latest_snapshot_ts(
    exchange: str,
    symbol: str,
    base_dir: Path | str = DEFAULT_MODELED_SNAPSHOT_ROOT,
) -> str | None:
    """Get the latest snapshot timestamp for a given exchange and symbol."""
    snapshots = list_available_snapshots(exchange, symbol, base_dir)
    return snapshots[0] if snapshots else None


def get_latest_available_snapshot_ts(
    exchange: str,
    symbol: str,
    model_id: str,
    base_dir: Path | str = DEFAULT_MODELED_SNAPSHOT_ROOT,
) -> str | None:
    """Get the newest snapshot timestamp whose requested model is actually consumable."""
    base_dir = Path(base_dir)
    for snapshot_ts in list_available_snapshots(exchange, symbol, base_dir):
        manifest = load_manifest(exchange, symbol, snapshot_ts, base_dir)
        if not manifest:
            continue

        model_entry = manifest.get("models", {}).get(model_id)
        if not model_entry or model_entry.get("availability_status") != "available":
            continue

        artifact_rel_path = model_entry.get("artifact_path")
        if not artifact_rel_path:
            continue

        artifact_path = base_dir / exchange / artifact_rel_path
        if artifact_path.exists():
            return snapshot_ts

    return None

def load_manifest(
    exchange: str,
    symbol: str,
    snapshot_ts: str,
    base_dir: Path | str = DEFAULT_MODELED_SNAPSHOT_ROOT,
) -> dict[str, Any] | None:
    """Load the manifest for a specific snapshot."""
    base_dir = Path(base_dir)
    manifest_path = base_dir / exchange / "manifests" / symbol.upper() / f"{snapshot_ts}.json"
    if not manifest_path.exists():
        return None
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_artifact(
    exchange: str,
    symbol: str,
    snapshot_ts: str,
    model_id: str,
    base_dir: Path | str = DEFAULT_MODELED_SNAPSHOT_ROOT,
) -> dict[str, Any] | None:
    """Load a specific artifact using the manifest to find its path."""
    manifest = load_manifest(exchange, symbol, snapshot_ts, base_dir)
    if not manifest:
        return None
    
    model_entry = manifest.get("models", {}).get(model_id)
    if not model_entry or model_entry.get("availability_status") != "available":
        return None
    
    artifact_rel_path = model_entry.get("artifact_path")
    if not artifact_rel_path:
        return None
    
    artifact_path = Path(base_dir) / exchange / artifact_rel_path
    if not artifact_path.exists():
        return None
    
    with open(artifact_path, "r", encoding="utf-8") as f:
        return json.load(f)
