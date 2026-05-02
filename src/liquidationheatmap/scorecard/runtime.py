"""
Runtime evidence models and artifact writer for scorecard.
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel

from src.liquidationheatmap.scorecard.calibration import CalibrationMetadataEntry


class ScorecardQualitySummary(BaseModel):
    snapshot_coverage_status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
    price_path_coverage_status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
    volume_coverage_status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
    liquidation_confirmation_status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
    schema_validation_status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
    reproducibility_hash: str


class ScorecardEvidenceDetails(BaseModel):
    artifact_path: str
    summary_path: str
    artifact_generated_at: datetime
    artifact_age_secs: int
    adaptive_mode: bool
    experts: List[str]
    symbols: List[str]
    slice_count: int
    observation_count: int
    dominance_row_count: int
    coverage_gap_count: int
    blocking_issues: List[str]
    quality: ScorecardQualitySummary
    calibration_metadata: Dict[str, CalibrationMetadataEntry]
    artifact_links: Dict[str, str]


class ScorecardErrorDetails(BaseModel):
    blocking_issues: List[str]


class ScorecardEvidenceEnvelope(BaseModel):
    provider_id: str = "rektslug"
    schema_version: str = "1.0.0"
    generated_at: datetime
    status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
    freshness_sla_secs: int = 86400
    last_error: Optional[str] = None
    details: ScorecardEvidenceDetails | ScorecardErrorDetails


import json
import os
import hashlib
from pathlib import Path
from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle


class ScorecardArtifactWriter:
    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def canonicalize_bundle(self, bundle: ExpertScorecardBundle) -> str:
        return json.dumps(bundle.model_dump(mode="json"), sort_keys=True, default=str)

    def canonicalize_details(self, details: ScorecardEvidenceDetails) -> str:
        return json.dumps(details.model_dump(mode="json"), sort_keys=True, default=str)

    def compute_hash_from_json(self, json_str: str) -> str:
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def compute_hash(self, bundle: ExpertScorecardBundle) -> str:
        json_str = self.canonicalize_bundle(bundle)
        return self.compute_hash_from_json(json_str)

    def write_latest(
        self, bundle: ExpertScorecardBundle, details: ScorecardEvidenceDetails
    ) -> None:
        bundle_json = self.canonicalize_bundle(bundle)
        details_json = self.canonicalize_details(details)

        bundle_path = self.base_dir / "latest.json"
        summary_path = self.base_dir / "latest-summary.json"

        self._atomic_write(bundle_path, bundle_json)
        self._atomic_write(summary_path, details_json)

    def _atomic_write(self, target_path: Path, content: str) -> None:
        temp_path = target_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_path)
