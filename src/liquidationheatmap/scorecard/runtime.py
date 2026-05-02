"""Runtime evidence models and artifact writer for scorecard."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle
from src.liquidationheatmap.scorecard.calibration import CalibrationMetadataEntry

ScorecardStatus = Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]

SCORECARD_FRESHNESS_SLA_SECS = 86400
SCORECARD_PROVIDER_ID = "rektslug"
SCORECARD_SCHEMA_VERSION = "1.0.0"


class ScorecardQualitySummary(BaseModel):
    snapshot_coverage_status: ScorecardStatus
    price_path_coverage_status: ScorecardStatus
    volume_coverage_status: ScorecardStatus
    liquidation_confirmation_status: ScorecardStatus
    schema_validation_status: ScorecardStatus
    reproducibility_hash: str


class ScorecardEvidenceDetails(BaseModel):
    artifact_path: str
    summary_path: str
    artifact_generated_at: datetime
    artifact_age_secs: int
    adaptive_mode: bool
    experts: list[str]
    symbols: list[str]
    slice_count: int
    observation_count: int
    dominance_row_count: int
    coverage_gap_count: int
    blocking_issues: list[str]
    quality: ScorecardQualitySummary
    calibration_metadata: dict[str, CalibrationMetadataEntry]
    artifact_links: dict[str, str]


class ScorecardErrorDetails(BaseModel):
    blocking_issues: list[str]


class ScorecardEvidenceEnvelope(BaseModel):
    provider_id: str = SCORECARD_PROVIDER_ID
    schema_version: str = SCORECARD_SCHEMA_VERSION
    generated_at: datetime
    status: ScorecardStatus
    freshness_sla_secs: int = SCORECARD_FRESHNESS_SLA_SECS
    last_error: str | None = None
    details: ScorecardEvidenceDetails | ScorecardErrorDetails


class ScorecardArtifactWriter:
    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def canonicalize_bundle(self, bundle: ExpertScorecardBundle) -> str:
        return _canonical_json(bundle.model_dump(mode="json"))

    def canonicalize_details(self, details: ScorecardEvidenceDetails) -> str:
        return _canonical_json(details.model_dump(mode="json"))

    def compute_hash_from_json(self, json_str: str) -> str:
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def compute_hash(self, bundle: ExpertScorecardBundle) -> str:
        return self.compute_hash_from_json(self.canonicalize_bundle(bundle))

    def write_latest(
        self, bundle: ExpertScorecardBundle, details: ScorecardEvidenceDetails
    ) -> None:
        self._atomic_write(self.base_dir / "latest.json", self.canonicalize_bundle(bundle))
        self._atomic_write(
            self.base_dir / "latest-summary.json", self.canonicalize_details(details)
        )

    def _atomic_write(self, target_path: Path, content: str) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_name(f".{target_path.name}.tmp")
        with temp_path.open("w", encoding="utf-8") as file_obj:
            file_obj.write(content)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(temp_path, target_path)


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _coverage_gap_count(coverage_gaps: dict[str, Any] | None) -> int:
    if not coverage_gaps:
        return 0
    count = 0
    for value in coverage_gaps.values():
        if isinstance(value, list | tuple | set):
            count += len(value)
        elif isinstance(value, dict):
            count += len(value)
        elif value:
            count += 1
    return count


def _status_from_quality(
    quality: ScorecardQualitySummary, blocking_issues: list[str] | None = None
) -> ScorecardStatus:
    if blocking_issues:
        return "BLOCKED"

    statuses = [
        quality.snapshot_coverage_status,
        quality.price_path_coverage_status,
        quality.volume_coverage_status,
        quality.liquidation_confirmation_status,
        quality.schema_validation_status,
    ]
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if "UNAVAILABLE" in statuses:
        return "UNAVAILABLE"
    if "DEGRADED" in statuses:
        return "DEGRADED"
    return "HEALTHY"


def scorecard_status_from_details(details: ScorecardEvidenceDetails) -> ScorecardStatus:
    return _status_from_quality(details.quality, details.blocking_issues)


def classify_quality(
    bundle: ExpertScorecardBundle,
    artifact_age_secs: int,
    max_age_secs: int,
    hash_val: str,
    *,
    price_path_available: bool = True,
    volume_available: bool = True,
    liquidation_events_available: bool = True,
    require_observations: bool = False,
) -> tuple[ScorecardQualitySummary, list[str]]:
    blocking_issues: list[str] = []
    coverage_gap_count = _coverage_gap_count(bundle.coverage_gaps)

    schema_status: ScorecardStatus = "HEALTHY"
    if require_observations and not bundle.slices:
        schema_status = "BLOCKED"
        blocking_issues.append("scorecard bundle contains no slices")

    snapshot_status: ScorecardStatus = "HEALTHY"
    if artifact_age_secs > max_age_secs:
        snapshot_status = "DEGRADED"

    price_path_status: ScorecardStatus = "HEALTHY"
    if not price_path_available:
        price_path_status = "UNAVAILABLE"
        blocking_issues.append("price path source unavailable")
    elif coverage_gap_count:
        price_path_status = "DEGRADED"

    volume_status: ScorecardStatus = "HEALTHY" if volume_available else "DEGRADED"
    liquidation_status: ScorecardStatus = "HEALTHY" if liquidation_events_available else "DEGRADED"

    return (
        ScorecardQualitySummary(
            snapshot_coverage_status=snapshot_status,
            price_path_coverage_status=price_path_status,
            volume_coverage_status=volume_status,
            liquidation_confirmation_status=liquidation_status,
            schema_validation_status=schema_status,
            reproducibility_hash=hash_val,
        ),
        blocking_issues,
    )


def build_scorecard_details(
    *,
    bundle: ExpertScorecardBundle,
    artifact_path: Path,
    summary_path: Path,
    generated_at: datetime,
    adaptive_mode: bool,
    calibration_metadata: dict[str, CalibrationMetadataEntry],
    quality: ScorecardQualitySummary,
    blocking_issues: list[str],
) -> ScorecardEvidenceDetails:
    experts = sorted({scorecard_slice.expert_id for scorecard_slice in bundle.slices})
    symbols = sorted(
        {
            str(scorecard_slice.slice_dimensions.get("symbol"))
            for scorecard_slice in bundle.slices
            if scorecard_slice.slice_dimensions.get("symbol")
        }
    )

    return ScorecardEvidenceDetails(
        artifact_path=str(artifact_path),
        summary_path=str(summary_path),
        artifact_generated_at=generated_at,
        artifact_age_secs=0,
        adaptive_mode=adaptive_mode,
        experts=experts,
        symbols=symbols,
        slice_count=len(bundle.slices),
        observation_count=sum(scorecard_slice.sample_count for scorecard_slice in bundle.slices),
        dominance_row_count=len(bundle.dominance_rows or []),
        coverage_gap_count=_coverage_gap_count(bundle.coverage_gaps),
        blocking_issues=blocking_issues,
        quality=quality,
        calibration_metadata=calibration_metadata,
        artifact_links={
            "scorecard": str(artifact_path),
            "summary": str(summary_path),
        },
    )


def load_scorecard_details(scorecard_dir: Path) -> ScorecardEvidenceDetails:
    summary_path = scorecard_dir / "latest-summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return ScorecardEvidenceDetails.model_validate(payload)


def build_scorecard_envelope(
    *,
    status: ScorecardStatus,
    details: ScorecardEvidenceDetails | ScorecardErrorDetails,
    last_error: str | None = None,
) -> ScorecardEvidenceEnvelope:
    return ScorecardEvidenceEnvelope(
        generated_at=datetime.now(timezone.utc),
        status=status,
        last_error=last_error,
        details=details,
    )


def compact_scorecard_summary(details: ScorecardEvidenceDetails) -> dict[str, Any]:
    return {
        "artifact_generated_at": details.artifact_generated_at.isoformat().replace("+00:00", "Z"),
        "adaptive_mode": details.adaptive_mode,
        "experts": details.experts,
        "symbols": details.symbols,
        "observation_count": details.observation_count,
        "slice_count": details.slice_count,
        "coverage_gap_count": details.coverage_gap_count,
    }
