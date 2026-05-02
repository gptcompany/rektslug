"""
Integration tests for the /ops/scorecard/latest endpoint.
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.scorecard.runtime import ScorecardArtifactWriter
from src.liquidationheatmap.models.scorecard import ExpertScorecardBundle


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_scorecard_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.liquidationheatmap.api.routers.ops.get_scorecard_dir", lambda: tmp_path
    )
    return tmp_path


def test_get_scorecard_latest_healthy(client, mock_scorecard_dir):
    """T021: test GET /ops/scorecard/latest -> HEALTHY from valid artifact."""
    writer = ScorecardArtifactWriter(base_dir=mock_scorecard_dir)
    bundle = ExpertScorecardBundle(slices=[])

    # Needs valid JSON for latest.json and latest-summary.json
    (mock_scorecard_dir / "latest.json").write_text(bundle.model_dump_json())
    (mock_scorecard_dir / "latest-summary.json").write_text(
        json.dumps(
            {
                "artifact_path": "test",
                "summary_path": "test",
                "artifact_generated_at": "2026-05-02T16:00:00Z",
                "artifact_age_secs": 0,
                "adaptive_mode": True,
                "experts": [],
                "symbols": [],
                "slice_count": 0,
                "observation_count": 0,
                "dominance_row_count": 0,
                "coverage_gap_count": 0,
                "blocking_issues": [],
                "quality": {
                    "snapshot_coverage_status": "HEALTHY",
                    "price_path_coverage_status": "HEALTHY",
                    "volume_coverage_status": "HEALTHY",
                    "liquidation_confirmation_status": "HEALTHY",
                    "schema_validation_status": "HEALTHY",
                    "reproducibility_hash": "dummy",
                },
                "calibration_metadata": {},
                "artifact_links": {},
            }
        )
    )

    response = client.get("/ops/scorecard/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["details"]["slice_count"] == 0


def test_get_scorecard_latest_missing(client, mock_scorecard_dir):
    """T022: test missing artifact -> 503 UNAVAILABLE."""
    response = client.get("/ops/scorecard/latest")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "UNAVAILABLE"
    assert "scorecard artifact missing" in data["last_error"]


def test_get_scorecard_latest_invalid_schema(client, mock_scorecard_dir):
    """T023: test invalid schema -> fail-closed (UNAVAILABLE or BLOCKED)."""
    # Valid summary but invalid bundle
    (mock_scorecard_dir / "latest.json").write_text('{"invalid": "data"}')
    (mock_scorecard_dir / "latest-summary.json").write_text("{}")

    response = client.get("/ops/scorecard/latest")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] in ["UNAVAILABLE", "BLOCKED"]
    assert "validation" in data["last_error"].lower() or "schema" in data["last_error"].lower()


def test_methods_not_allowed(client):
    """T026b: test POST/PUT/DELETE -> 405."""
    assert client.post("/ops/scorecard/latest").status_code == 405
    assert client.put("/ops/scorecard/latest").status_code == 405
    assert client.delete("/ops/scorecard/latest").status_code == 405
