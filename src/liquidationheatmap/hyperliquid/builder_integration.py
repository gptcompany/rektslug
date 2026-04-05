"""Builder integration and mapping logic for Hyperliquid expert snapshots."""

from collections import defaultdict
from typing import Any

from src.liquidationheatmap.hyperliquid.snapshot_schema import (
    BucketGrid,
    ExpertSnapshotArtifact,
    validate_artifact,
)


def assign_research_policy_tag(expert_id: str) -> str:
    """Assign the correct research policy tag based on the expert ID."""
    if expert_id == "v1":
        return "canonical"
    if expert_id == "v2":
        return "shadow/control"
    if expert_id in ("v3", "v4", "v5"):
        return "experimental"
    return "experimental"


def strip_cache_references(source_metadata: dict[str, Any]) -> dict[str, Any]:
    """Ensure exported artifacts do not contain local data/cache/ paths."""
    cleaned = dict(source_metadata)
    # Remove any key that hints at a local cache path
    for k in list(cleaned.keys()):
        if "cache_path" in k or "local_path" in k:
            del cleaned[k]
        elif isinstance(cleaned[k], str) and "data/cache" in cleaned[k]:
            cleaned[k] = "REDACTED_LOCAL_PATH"
    return cleaned


def normalize_to_canonical_grid(
    distribution: dict[str, float], canonical_grid: BucketGrid
) -> dict[str, float]:
    """Normalize a distribution to the canonical grid by rebucketing."""
    if (
        canonical_grid.step is None
        or canonical_grid.min_price is None
        or canonical_grid.max_price is None
    ):
        # If it's a price_levels grid, just keep it as is or snap to nearest.
        # MVP states min/max/step is the accepted MVP grid form.
        return distribution

    step = canonical_grid.step
    min_price = canonical_grid.min_price
    max_price = canonical_grid.max_price

    normalized = defaultdict(float)
    for price_str, volume in distribution.items():
        price = float(price_str)

        # Snap to grid floor
        bucket_index = int((price - min_price) // step)
        bucket_price = min_price + (bucket_index * step)

        if bucket_price < min_price:
            bucket_price = min_price
        elif bucket_price > max_price:
            bucket_price = max_price

        normalized[str(bucket_price)] += volume

    return dict(normalized)


def map_builder_payload_to_artifact(
    expert_id: str, builder_payload: dict[str, Any]
) -> ExpertSnapshotArtifact:
    """Map a raw builder payload into a strict ExpertSnapshotArtifact."""
    payload = dict(builder_payload)
    payload["expert_id"] = expert_id
    payload["research_policy_tag"] = assign_research_policy_tag(expert_id)

    if "source_metadata" in payload:
        payload["source_metadata"] = strip_cache_references(payload["source_metadata"])

    return validate_artifact(payload)


def detect_builder_gap_failures(error_details: dict[str, Any]) -> dict[str, Any]:
    """
    Format explicit gap detections (e.g. unhandled margin abstractions)
    as failed_decode reasons rather than missing outputs.
    """
    return {"reason": error_details.get("error", "unknown_failure"), "details": error_details}
