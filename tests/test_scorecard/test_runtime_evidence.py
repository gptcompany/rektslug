"""
Tests for runtime evidence and artifact writer.
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle
from src.liquidationheatmap.scorecard.runtime import (
    CalibrationMetadataEntry,
    ScorecardEvidenceDetails,
    ScorecardQualitySummary,
)


def test_scorecard_evidence_models_valid():
    """Test valid instantiations of the models."""
    quality = ScorecardQualitySummary(
        snapshot_coverage_status="HEALTHY",
        price_path_coverage_status="HEALTHY",
        volume_coverage_status="HEALTHY",
        liquidation_confirmation_status="DEGRADED",
        schema_validation_status="HEALTHY",
        reproducibility_hash="deadbeef",
    )

    calib = CalibrationMetadataEntry(
        kind="governance_constant",
        name="freshness_sla_secs",
        value=86400,
        method="static",
        reason="Test",
    )

    details = ScorecardEvidenceDetails(
        artifact_path="test.json",
        summary_path="test-summary.json",
        artifact_generated_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        artifact_age_secs=100,
        adaptive_mode=True,
        experts=["e1"],
        symbols=["BTCUSDT"],
        slice_count=10,
        observation_count=100,
        dominance_row_count=5,
        coverage_gap_count=0,
        blocking_issues=[],
        quality=quality,
        calibration_metadata={"sla": calib},
        artifact_links={},
    )

    assert details.artifact_age_secs == 100
    assert details.quality.snapshot_coverage_status == "HEALTHY"

def test_calibration_metadata_invalid_kind():
    """Test kind literal constraint."""
    with pytest.raises(ValidationError):
        CalibrationMetadataEntry(
            kind="invalid_kind",
            name="test",
            value=1,
            method="test",
            reason="test",
        )

def test_expert_scorecard_bundle_loads_in_runtime():
    """T008b: Test that an empty/minimal bundle can be processed conceptually by runtime layer."""
    bundle = ExpertScorecardBundle(slices=[])
    assert bundle.slices == []

