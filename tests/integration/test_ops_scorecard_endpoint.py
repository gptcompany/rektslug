"""Integration tests for the /ops/scorecard/latest endpoint."""

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle, ExpertScorecardSlice
from src.liquidationheatmap.scorecard.runtime import (
    ScorecardEvidenceDetails,
    ScorecardQualitySummary,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_scorecard_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.liquidationheatmap.api.routers.ops.get_scorecard_dir", lambda: tmp_path
    )
    return tmp_path


def _slice() -> ExpertScorecardSlice:
    dimensions = {
        "symbol": "BTCUSDT",
        "side": "long",
        "distance_bucket": "all",
        "confidence_bucket": "all",
        "regime": "stable",
    }
    return ExpertScorecardSlice(
        expert_id="v1",
        slice_id=ExpertScorecardSlice.generate_slice_id(
            "v1", "BTCUSDT", "long", "all", "all", "stable"
        ),
        slice_dimensions=dimensions,
        sample_count=10,
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


def _summary(status: str = "HEALTHY") -> dict:
    return ScorecardEvidenceDetails(
        artifact_path="test",
        summary_path="test-summary",
        artifact_generated_at=datetime(2026, 5, 2, 16, 0, tzinfo=timezone.utc),
        artifact_age_secs=0,
        adaptive_mode=True,
        experts=["v1"],
        symbols=["BTCUSDT"],
        slice_count=1,
        observation_count=10,
        dominance_row_count=0,
        coverage_gap_count=0 if status == "HEALTHY" else 1,
        blocking_issues=[],
        quality=ScorecardQualitySummary(
            snapshot_coverage_status="HEALTHY",
            price_path_coverage_status=status,
            volume_coverage_status="HEALTHY",
            liquidation_confirmation_status="HEALTHY",
            schema_validation_status="HEALTHY",
            reproducibility_hash="dummy",
        ),
        calibration_metadata={},
        artifact_links={"scorecard": "test", "summary": "test-summary"},
    ).model_dump(mode="json")


def _write_artifacts(scorecard_dir, *, quality_status: str = "HEALTHY"):
    bundle = ExpertScorecardBundle(slices=[_slice()])
    (scorecard_dir / "latest.json").write_text(bundle.model_dump_json(), encoding="utf-8")
    (scorecard_dir / "latest-summary.json").write_text(
        json.dumps(_summary(quality_status)), encoding="utf-8"
    )


def test_get_scorecard_latest_healthy(client, mock_scorecard_dir):
    _write_artifacts(mock_scorecard_dir)

    response = client.get("/ops/scorecard/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["provider_id"] == "rektslug"
    assert data["schema_version"] == "1.0.0"
    assert data["freshness_sla_secs"] == 86400
    assert data["last_error"] is None
    assert data["status"] == "HEALTHY"
    assert data["details"]["slice_count"] == 1
    assert data["details"]["observation_count"] == 10


def test_get_scorecard_latest_degraded_when_any_quality_dimension_degraded(
    client, mock_scorecard_dir
):
    _write_artifacts(mock_scorecard_dir, quality_status="DEGRADED")

    response = client.get("/ops/scorecard/latest")
    assert response.status_code == 200
    assert response.json()["status"] == "DEGRADED"


def test_get_scorecard_latest_missing(client, mock_scorecard_dir):
    response = client.get("/ops/scorecard/latest")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "UNAVAILABLE"
    assert data["freshness_sla_secs"] == 86400
    assert "scorecard artifact missing" in data["last_error"]


def test_get_scorecard_latest_invalid_schema(client, mock_scorecard_dir):
    (mock_scorecard_dir / "latest.json").write_text('{"invalid": "data"}', encoding="utf-8")
    (mock_scorecard_dir / "latest-summary.json").write_text(
        json.dumps(_summary()), encoding="utf-8"
    )

    response = client.get("/ops/scorecard/latest")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "BLOCKED"
    assert "validation" in data["last_error"].lower()


def test_methods_not_allowed(client):
    assert client.post("/ops/scorecard/latest").status_code == 405
    assert client.put("/ops/scorecard/latest").status_code == 405
    assert client.delete("/ops/scorecard/latest").status_code == 405


def test_ops_summary_includes_scorecard(client, mock_scorecard_dir, monkeypatch):
    async def mock_get_signal_status():
        from pydantic import BaseModel

        class MockSigStatus(BaseModel):
            connected: bool = True

        return MockSigStatus()

    async def mock_get_continuous_report():
        from pydantic import BaseModel

        class MockContReport(BaseModel):
            report_status: str = "ok"
            persistence_consistent: bool = True
            feedback_published: int = 1
            feedback_persisted: int = 1

        return MockContReport()

    monkeypatch.setattr(
        "src.liquidationheatmap.api.routers.ops.get_signal_status", mock_get_signal_status
    )
    monkeypatch.setattr(
        "src.liquidationheatmap.api.routers.ops.get_continuous_report",
        mock_get_continuous_report,
    )
    _write_artifacts(mock_scorecard_dir)

    response = client.get("/ops/summary")
    assert response.status_code == 200
    details = response.json()["details"]
    assert details["scorecard_status"] == "HEALTHY"

    summary = details["scorecard_summary"]
    assert summary["artifact_generated_at"] == "2026-05-02T16:00:00Z"
    assert summary["adaptive_mode"] is True
    assert summary["experts"] == ["v1"]
    assert summary["symbols"] == ["BTCUSDT"]
    assert summary["observation_count"] == 10
    assert summary["slice_count"] == 1
    assert summary["coverage_gap_count"] == 0
    assert "calibration_metadata" not in summary
    assert "artifact_links" not in summary


def test_ops_summary_degrades_when_scorecard_quality_degraded(
    client, mock_scorecard_dir, monkeypatch
):
    async def mock_get_signal_status():
        from pydantic import BaseModel

        class MockSigStatus(BaseModel):
            connected: bool = True

        return MockSigStatus()

    async def mock_get_continuous_report():
        from pydantic import BaseModel

        class MockContReport(BaseModel):
            report_status: str = "ok"
            persistence_consistent: bool = True
            feedback_published: int = 1
            feedback_persisted: int = 1

        return MockContReport()

    monkeypatch.setattr(
        "src.liquidationheatmap.api.routers.ops.get_signal_status", mock_get_signal_status
    )
    monkeypatch.setattr(
        "src.liquidationheatmap.api.routers.ops.get_continuous_report",
        mock_get_continuous_report,
    )
    _write_artifacts(mock_scorecard_dir, quality_status="DEGRADED")

    response = client.get("/ops/summary")
    assert response.status_code == 200
    assert response.json()["details"]["scorecard_status"] == "DEGRADED"
