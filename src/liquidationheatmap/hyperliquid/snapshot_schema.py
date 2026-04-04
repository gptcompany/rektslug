"""Schema definitions and validation for Hyperliquid expert snapshots."""

import re
from dataclasses import dataclass
from typing import Any

# ISO 8601 UTC regex matching YYYY-MM-DDTHH:MM:SSZ (or with fractional seconds)
ISO8601_Z_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


@dataclass
class BucketGrid:
    min_price: float | None = None
    max_price: float | None = None
    step: float | None = None
    price_levels: list[float] | None = None

    def __post_init__(self):
        if self.price_levels is not None:
            if not isinstance(self.price_levels, list):
                raise ValueError("price_levels must be a list")
            self.price_levels = [float(x) for x in self.price_levels]
        else:
            if self.min_price is None or self.max_price is None or self.step is None:
                raise ValueError(
                    "Invalid bucket grid: must provide either price_levels or min_price, max_price, and step"
                )
            self.min_price = float(self.min_price)
            self.max_price = float(self.max_price)
            self.step = float(self.step)


@dataclass
class ExpertSnapshotArtifact:
    expert_id: str
    symbol: str
    snapshot_ts: str
    reference_price: float
    bucket_grid: BucketGrid
    long_distribution: dict[str, float]
    short_distribution: dict[str, float]
    research_policy_tag: str
    source_metadata: dict[str, Any]
    generation_metadata: dict[str, Any]


def validate_artifact(payload: dict[str, Any]) -> ExpertSnapshotArtifact:
    """Validate a raw dictionary against the ExpertSnapshotArtifact contract."""

    required_fields = [
        "expert_id",
        "symbol",
        "snapshot_ts",
        "reference_price",
        "bucket_grid",
        "long_distribution",
        "short_distribution",
        "research_policy_tag",
        "source_metadata",
        "generation_metadata",
    ]

    for field in required_fields:
        if field not in payload:
            raise ValueError(f"Missing required field: {field}")

    # Validate timestamp format
    snapshot_ts = str(payload["snapshot_ts"])
    if not ISO8601_Z_REGEX.match(snapshot_ts):
        raise ValueError(f"snapshot_ts must be UTC ISO8601 with 'Z' suffix: {snapshot_ts}")

    # Validate generation metadata required fields
    gen_meta = payload["generation_metadata"]
    if not isinstance(gen_meta, dict):
        raise ValueError("generation_metadata must be an object")

    for gm_field in ["run_id", "run_reason", "run_ts", "last_actual_run_ts", "producer_version"]:
        if gm_field not in gen_meta:
            raise ValueError(f"Missing required generation_metadata field: {gm_field}")

    if not ISO8601_Z_REGEX.match(str(gen_meta["run_ts"])):
        raise ValueError("run_ts must be UTC ISO8601 with 'Z' suffix")

    if not ISO8601_Z_REGEX.match(str(gen_meta["last_actual_run_ts"])):
        raise ValueError("last_actual_run_ts must be UTC ISO8601 with 'Z' suffix")

    # Validate source metadata
    src_meta = payload["source_metadata"]
    if not isinstance(src_meta, dict):
        raise ValueError("source_metadata must be an object")
    if "builder_family" not in src_meta:
        raise ValueError("Missing required source_metadata field: builder_family")
    if "input_identity" not in src_meta:
        raise ValueError("Missing required source_metadata field: input_identity")
    if not isinstance(src_meta["input_identity"], dict):
        raise ValueError("input_identity must be an object")

    # Parse and validate bucket grid
    bg_payload = payload["bucket_grid"]
    if not isinstance(bg_payload, dict):
        raise ValueError("bucket_grid must be an object")

    bucket_grid = BucketGrid(
        min_price=bg_payload.get("min_price"),
        max_price=bg_payload.get("max_price"),
        step=bg_payload.get("step"),
        price_levels=bg_payload.get("price_levels"),
    )

    # Parse distributions
    long_dist = {str(k): float(v) for k, v in payload["long_distribution"].items()}
    short_dist = {str(k): float(v) for k, v in payload["short_distribution"].items()}

    return ExpertSnapshotArtifact(
        expert_id=str(payload["expert_id"]),
        symbol=str(payload["symbol"]),
        snapshot_ts=snapshot_ts,
        reference_price=float(payload["reference_price"]),
        bucket_grid=bucket_grid,
        long_distribution=long_dist,
        short_distribution=short_dist,
        research_policy_tag=str(payload["research_policy_tag"]),
        source_metadata=src_meta,
        generation_metadata=gen_meta,
    )
