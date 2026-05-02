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
