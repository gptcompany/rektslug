"""Tests for scorecard runtime evidence and artifact writer."""

import importlib.util
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle, ExpertScorecardSlice
from src.liquidationheatmap.scorecard.runtime import (
    CalibrationMetadataEntry,
    ScorecardArtifactWriter,
    ScorecardEvidenceDetails,
    ScorecardQualitySummary,
    build_scorecard_details,
    classify_quality,
    compact_scorecard_summary,
    scorecard_status_from_details,
)


def _slice(
    *,
    expert_id: str = "v1",
    symbol: str = "BTCUSDT",
    sample_count: int = 10,
) -> ExpertScorecardSlice:
    dimensions = {
        "symbol": symbol,
        "side": "long",
        "distance_bucket": "all",
        "confidence_bucket": "all",
        "regime": "stable",
    }
    return ExpertScorecardSlice(
        expert_id=expert_id,
        slice_id=ExpertScorecardSlice.generate_slice_id(
            expert_id, symbol, "long", "all", "all", "stable"
        ),
        slice_dimensions=dimensions,
        sample_count=sample_count,
        touch_count=5,
        touch_probability=0.5,
        liquidation_match_count=2,
        liquidation_match_probability_given_touch=0.4,
        mfe_quantiles={"p10": 1, "p25": 2, "p50": 3, "p75": 4, "p90": 5},
        mae_quantiles={"p10": 1, "p25": 2, "p50": 3, "p75": 4, "p90": 5},
        time_to_touch_quantiles={"p10": 1, "p25": 2, "p50": 3, "p75": 4, "p90": 5},
        time_to_liquidation_confirm_quantiles={
            "p10": 1,
            "p25": 2,
            "p50": 3,
            "p75": 4,
            "p90": 5,
        },
        low_sample_flag=False,
    )


def _details(
    tmp_path: Path, quality: ScorecardQualitySummary | None = None
) -> ScorecardEvidenceDetails:
    bundle = ExpertScorecardBundle(slices=[_slice()])
    if quality is None:
        quality, blocking_issues = classify_quality(
            bundle,
            artifact_age_secs=0,
            max_age_secs=86400,
            hash_val="hash",
            require_observations=True,
        )
    else:
        blocking_issues = []

    return build_scorecard_details(
        bundle=bundle,
        artifact_path=tmp_path / "latest.json",
        summary_path=tmp_path / "latest-summary.json",
        generated_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        adaptive_mode=True,
        calibration_metadata={},
        quality=quality,
        blocking_issues=blocking_issues,
    )


def test_quality_classifier_healthy():
    bundle = ExpertScorecardBundle(slices=[_slice()])
    quality, blocking = classify_quality(
        bundle,
        artifact_age_secs=10,
        max_age_secs=86400,
        hash_val="hash",
        require_observations=True,
    )
    assert quality.schema_validation_status == "HEALTHY"
    assert quality.snapshot_coverage_status == "HEALTHY"
    assert not blocking


def test_quality_classifier_stale():
    bundle = ExpertScorecardBundle(slices=[_slice()])
    quality, _blocking = classify_quality(
        bundle,
        artifact_age_secs=90000,
        max_age_secs=86400,
        hash_val="hash",
    )
    assert quality.snapshot_coverage_status == "DEGRADED"


def test_quality_classifier_coverage_gaps():
    bundle = ExpertScorecardBundle(slices=[_slice()], coverage_gaps={"gaps": [1, 2, 3]})
    quality, _blocking = classify_quality(
        bundle,
        artifact_age_secs=10,
        max_age_secs=86400,
        hash_val="hash",
    )
    assert quality.price_path_coverage_status == "DEGRADED"


def test_quality_classifier_blocking_schema_when_real_generation_has_no_slices():
    bundle = ExpertScorecardBundle(slices=[])
    quality, blocking = classify_quality(
        bundle,
        artifact_age_secs=10,
        max_age_secs=86400,
        hash_val="hash",
        require_observations=True,
    )
    assert quality.schema_validation_status == "BLOCKED"
    assert blocking == ["scorecard bundle contains no slices"]


def test_scorecard_status_uses_all_quality_dimensions(tmp_path):
    quality = ScorecardQualitySummary(
        snapshot_coverage_status="HEALTHY",
        price_path_coverage_status="DEGRADED",
        volume_coverage_status="HEALTHY",
        liquidation_confirmation_status="HEALTHY",
        schema_validation_status="HEALTHY",
        reproducibility_hash="hash",
    )
    assert scorecard_status_from_details(_details(tmp_path, quality)) == "DEGRADED"


def test_cli_missing_snapshots_fails(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate-scorecard-evidence.py",
            "--snapshot-root",
            str(tmp_path / "missing"),
            "--price-path",
            str(tmp_path / "price_path.json"),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not (tmp_path / "latest.json").exists()


def test_cli_requires_real_price_path(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent)
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / "manifests").mkdir(parents=True)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate-scorecard-evidence.py",
            "--snapshot-root",
            str(snapshot_root),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--price-path" in result.stderr


def test_cli_successful_generation_uses_loaded_price_path(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "generate_scorecard_evidence", "scripts/generate-scorecard-evidence.py"
    )
    gen_module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(gen_module)

    observed = {}

    class DummyPipeline:
        def __init__(self, *args, **kwargs):
            pass

        def run_from_retained_snapshots(self, *args, **kwargs):
            observed.update(kwargs)
            return ExpertScorecardBundle(slices=[_slice()]).model_dump_json()

    monkeypatch.setattr(gen_module, "ScorecardPipeline", DummyPipeline)

    snapshot_root = tmp_path / "dummy_snapshots"
    (snapshot_root / "manifests").mkdir(parents=True)
    price_path = tmp_path / "price_path.json"
    price_path.write_text(
        '[{"timestamp":"2026-05-02T00:00:00Z","price":100.0,"volume":10.0}]',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate-scorecard-evidence.py",
            "--output-dir",
            str(tmp_path),
            "--snapshot-root",
            str(snapshot_root),
            "--price-path",
            str(price_path),
        ],
    )

    assert gen_module.main() == 0
    assert observed["price_path"] == [
        {"timestamp": "2026-05-02T00:00:00Z", "price": 100.0, "volume": 10.0}
    ]
    assert observed["expected_experts"] == ["v1", "v3", "v4", "v5"]
    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "latest-summary.json").exists()


def test_artifact_writer_writes_latest_files(tmp_path):
    writer = ScorecardArtifactWriter(base_dir=tmp_path)
    bundle = ExpertScorecardBundle(slices=[_slice()])

    writer.write_latest(bundle, _details(tmp_path))

    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "latest-summary.json").exists()


def test_artifact_writer_reproducibility(tmp_path):
    writer = ScorecardArtifactWriter(base_dir=tmp_path)
    bundle = ExpertScorecardBundle(slices=[_slice()], adaptive_parameters={"a": 1, "b": 2})

    json1 = writer.canonicalize_bundle(bundle)
    json2 = writer.canonicalize_bundle(bundle)

    assert json1 == json2
    assert writer.compute_hash(bundle) == writer.compute_hash_from_json(json1)


def test_scorecard_evidence_models_valid(tmp_path):
    details = _details(tmp_path)
    assert details.artifact_age_secs == 0
    assert details.quality.snapshot_coverage_status == "HEALTHY"
    assert details.experts == ["v1"]
    assert details.symbols == ["BTCUSDT"]
    assert compact_scorecard_summary(details)["slice_count"] == 1


def test_calibration_metadata_invalid_kind():
    with pytest.raises(ValidationError):
        CalibrationMetadataEntry(
            kind="invalid_kind",
            name="test",
            value=1,
            method="test",
            reason="test",
        )


def test_expert_scorecard_bundle_loads_in_runtime(tmp_path):
    bundle = ExpertScorecardBundle(slices=[_slice()])
    writer = ScorecardArtifactWriter(base_dir=tmp_path)
    details = _details(tmp_path)
    writer.write_latest(bundle, details)
    assert (tmp_path / "latest.json").read_text(encoding="utf-8")
