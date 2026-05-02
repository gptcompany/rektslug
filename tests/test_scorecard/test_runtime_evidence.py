"""
Tests for runtime evidence and artifact writer.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle
import os
from pathlib import Path
from src.liquidationheatmap.scorecard.runtime import ScorecardArtifactWriter
import subprocess
import sys


def test_cli_missing_snapshots_fails(tmp_path):
    """T016: Test that missing snapshots exits non-zero, no green artifact."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate-scorecard-evidence.py",
            "--snapshot-root",
            str(tmp_path / "missing"),
        ],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert not (tmp_path / "latest.json").exists()


def test_cli_successful_generation(tmp_path, monkeypatch):
    """T015: Test successful adaptive evidence generation via CLI."""
    # We'll mock the pipeline's run_from_retained_snapshots method
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent)

    import importlib.util
    spec = importlib.util.spec_from_file_location("generate_scorecard_evidence", "scripts/generate-scorecard-evidence.py")
    gen_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen_module)

    # Mock pipeline
    class DummyPipeline:
        def __init__(self, *args, **kwargs):
            pass
        def run_from_retained_snapshots(self, *args, **kwargs):
            return ExpertScorecardBundle(slices=[]).model_dump_json()

    monkeypatch.setattr(gen_module, "ScorecardPipeline", DummyPipeline)

    # Set up dummy snapshot root
    snapshot_root = tmp_path / "dummy_snapshots"
    snapshot_root.mkdir()
    (snapshot_root / "dummy.json").touch()
    (snapshot_root / "manifests").mkdir()

    monkeypatch.setattr(sys, "argv", ["generate-scorecard-evidence.py", "--output-dir", str(tmp_path), "--snapshot-root", str(snapshot_root)])

    try:
        gen_module.main()
    except SystemExit as e:
        assert e.code == 0

    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "latest-summary.json").exists()


def test_artifact_writer_writes_latest_files(tmp_path):
    """T010: Test that valid bundle writes latest.json and latest-summary.json."""
    writer = ScorecardArtifactWriter(base_dir=tmp_path)
    bundle = ExpertScorecardBundle(slices=[])

    details = ScorecardEvidenceDetails(
        artifact_path=str(tmp_path / "latest.json"),
        summary_path=str(tmp_path / "latest-summary.json"),
        artifact_generated_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        artifact_age_secs=0,
        adaptive_mode=True,
        experts=[],
        symbols=[],
        slice_count=0,
        observation_count=0,
        dominance_row_count=0,
        coverage_gap_count=0,
        blocking_issues=[],
        quality=ScorecardQualitySummary(
            snapshot_coverage_status="HEALTHY",
            price_path_coverage_status="HEALTHY",
            volume_coverage_status="HEALTHY",
            liquidation_confirmation_status="HEALTHY",
            schema_validation_status="HEALTHY",
            reproducibility_hash="dummy",
        ),
        calibration_metadata={},
        artifact_links={},
    )

    writer.write_latest(bundle, details)

    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "latest-summary.json").exists()


def test_artifact_writer_reproducibility(tmp_path):
    """T011: Test identical inputs produce byte-identical JSON and same hash."""
    writer = ScorecardArtifactWriter(base_dir=tmp_path)
    bundle = ExpertScorecardBundle(slices=[], adaptive_parameters={"a": 1, "b": 2})

    json1 = writer.canonicalize_bundle(bundle)
    json2 = writer.canonicalize_bundle(bundle)

    assert json1 == json2

    hash1 = writer.compute_hash(bundle)
    hash2 = writer.compute_hash(bundle)

    assert hash1 == hash2
    assert hash1 == writer.compute_hash_from_json(json1)


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
