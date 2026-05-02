from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.api.routers.ops import _load_shadow_report, _shadow_producer_status
from src.liquidationheatmap.signals import ContinuousReport, SignalStatus

client = TestClient(app)


@pytest.fixture
def mock_evidence():
    return {
        "spec_id": "040",
        "gate_status": "READY_FOR_REVIEW",
        "generated_at": "2026-04-22T21:30:07Z",
        "runtime_snapshot_path": "/some/path/continuous_runtime_report.json",
        "continuous_report": {
            "session_started_at": "2026-04-22T21:29:32Z",
            "timestamp": "2026-04-22T21:29:54Z",
            "runtime_seconds": 22.5,
            "feedback_published": 1,
            "feedback_persisted": 1,
            "positions_opened": 1,
            "positions_closed": 1,
            "residual_open_positions": 0,
            "residual_open_orders": 0,
        },
    }


def test_ops_summary_success(mock_evidence):
    with patch(
        "src.liquidationheatmap.api.routers.ops.get_signal_status", new_callable=AsyncMock
    ) as mock_status:
        mock_status.return_value = SignalStatus(
            connected=True,
            last_publish="2025-12-28T10:30:00Z",
            signals_published_24h=96,
            feedback_received_24h=12,
        )
        with patch(
            "src.liquidationheatmap.api.routers.ops.get_continuous_report", new_callable=AsyncMock
        ) as mock_report:
            mock_report.return_value = ContinuousReport(
                session_started_at=datetime.now(timezone.utc),
                timestamp=datetime.now(timezone.utc),
                runtime_seconds=100.0,
                signals_seen=10,
                signals_accepted=5,
                orders_submitted=5,
                positions_opened=5,
                positions_closed=5,
                feedback_published=5,
                feedback_persisted=5,
                report_status="ok",
                blocking_issues=[],
            )
            with patch(
                "src.liquidationheatmap.api.routers.ops._find_latest_spec040_evidence"
            ) as mock_find:
                mock_find.return_value = mock_evidence
                with patch(
                    "src.liquidationheatmap.api.routers.ops._shadow_producer_status"
                ) as mock_shadow:
                    mock_shadow.return_value = "HEALTHY"
                    with patch(
                        "src.liquidationheatmap.api.routers.ops._load_shadow_report"
                    ) as mock_shadow_report:
                        mock_shadow_report.return_value = (
                            "HEALTHY",
                            {"summary": {"signals_seen": 10}},
                        )
                        with patch(
                            "src.liquidationheatmap.api.routers.ops.load_scorecard_details"
                        ) as mock_sc:
                            from src.liquidationheatmap.scorecard.runtime import (
                                ScorecardEvidenceDetails,
                                ScorecardQualitySummary,
                            )

                            mock_sc.return_value = ScorecardEvidenceDetails(
                                artifact_path="test",
                                summary_path="test",
                                artifact_generated_at=datetime.now(timezone.utc),
                                artifact_age_secs=0,
                                adaptive_mode=True,
                                experts=["v1"],
                                symbols=["BTCUSDT"],
                                slice_count=1,
                                observation_count=10,
                                dominance_row_count=0,
                                coverage_gap_count=0,
                                blocking_issues=[],
                                quality=ScorecardQualitySummary(
                                    snapshot_coverage_status="HEALTHY",
                                    price_path_coverage_status="HEALTHY",
                                    volume_coverage_status="HEALTHY",
                                    liquidation_confirmation_status="HEALTHY",
                                    schema_validation_status="HEALTHY",
                                    reproducibility_hash="test",
                                ),
                                calibration_metadata={},
                                artifact_links={},
                            )
                            response = client.get("/ops/summary")
                        assert response.status_code == 200
                        data = response.json()
                        assert data["provider_id"] == "rektslug"
                        assert data["status"] == "HEALTHY"
                        assert data["details"]["redis"] == "HEALTHY"
                        assert isinstance(data["details"]["signals_status"], dict)
                        assert data["details"]["signals_status"]["connected"] is True
                        assert data["details"]["signals_status_level"] == "HEALTHY"
                        assert data["details"]["shadow_producer"] == "HEALTHY"
                        assert data["details"]["shadow_consumer"] == "HEALTHY"
                        assert data["details"]["shadow_report_status"] == "HEALTHY"
                        assert data["details"]["feedback_consumer"] == "HEALTHY"
                        assert data["details"]["continuous_report_status"] == "HEALTHY"
                        assert data["details"]["evidence_spec_040_latest_status"] == "HEALTHY"
                        assert "ownership_note" in data["details"]


def test_shadow_producer_status_healthy_with_fresh_manifests(tmp_path):
    for symbol in ("BTCUSDT", "ETHUSDT"):
        manifest_dir = (
            tmp_path
            / "data"
            / "validation"
            / "expert_snapshots"
            / "hyperliquid"
            / "manifests"
            / symbol
        )
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "2026-05-02T09:42:05Z.json").write_text("{}", encoding="utf-8")

    assert _shadow_producer_status(repo_root=tmp_path, max_age_secs=600) == "HEALTHY"


def test_shadow_producer_status_unavailable_when_symbol_missing(tmp_path):
    manifest_dir = (
        tmp_path
        / "data"
        / "validation"
        / "expert_snapshots"
        / "hyperliquid"
        / "manifests"
        / "BTCUSDT"
    )
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "2026-05-02T09:42:05Z.json").write_text("{}", encoding="utf-8")

    assert _shadow_producer_status(repo_root=tmp_path, max_age_secs=600) == "UNAVAILABLE"


def test_load_shadow_report_healthy_with_fresh_report(tmp_path):
    report_path = tmp_path / "shadow_report.json"
    report_path.write_text(
        '{"summary": {"signals_seen": 10, "accepted": 2}, "signals": []}',
        encoding="utf-8",
    )

    status, payload = _load_shadow_report(path=report_path, max_age_secs=600)

    assert status == "HEALTHY"
    assert payload["summary"]["signals_seen"] == 10


def test_ops_summary_degraded_when_no_continuous_report(mock_evidence):
    from fastapi import HTTPException

    with patch(
        "src.liquidationheatmap.api.routers.ops.get_signal_status", new_callable=AsyncMock
    ) as mock_status:
        mock_status.return_value = SignalStatus(
            connected=True,
            last_publish="2025-12-28T10:30:00Z",
            signals_published_24h=96,
            feedback_received_24h=12,
        )
        with patch(
            "src.liquidationheatmap.api.routers.ops.get_continuous_report", new_callable=AsyncMock
        ) as mock_report:
            mock_report.side_effect = HTTPException(
                status_code=503, detail="Continuous report unavailable"
            )
            with patch(
                "src.liquidationheatmap.api.routers.ops._find_latest_spec040_evidence"
            ) as mock_find:
                mock_find.return_value = mock_evidence
                response = client.get("/ops/summary")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] != "HEALTHY"
                assert data["details"]["continuous_report_status"] == "UNAVAILABLE"
                assert data["details"]["evidence_spec_040_latest_status"] == "HEALTHY"


def test_ops_summary_degraded_when_no_evidence():
    with patch(
        "src.liquidationheatmap.api.routers.ops.get_signal_status", new_callable=AsyncMock
    ) as mock_status:
        mock_status.return_value = SignalStatus(
            connected=True,
            last_publish="2025-12-28T10:30:00Z",
            signals_published_24h=96,
            feedback_received_24h=12,
        )
        with patch(
            "src.liquidationheatmap.api.routers.ops.get_continuous_report", new_callable=AsyncMock
        ) as mock_report:
            mock_report.return_value = ContinuousReport(
                session_started_at=datetime.now(timezone.utc),
                timestamp=datetime.now(timezone.utc),
                runtime_seconds=100.0,
                signals_seen=10,
                signals_accepted=5,
                orders_submitted=5,
                positions_opened=5,
                positions_closed=5,
                feedback_published=5,
                feedback_persisted=5,
                report_status="ok",
                blocking_issues=[],
            )
            with patch(
                "src.liquidationheatmap.api.routers.ops._find_latest_spec040_evidence"
            ) as mock_find:
                mock_find.return_value = None
                response = client.get("/ops/summary")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "DEGRADED"
                assert data["details"]["latest_evidence_spec040"] is None
                assert data["details"]["evidence_spec_040_latest_status"] == "UNAVAILABLE"


def test_ops_shadow_report_fail_closed():
    with patch("src.liquidationheatmap.api.routers.ops._load_shadow_report") as mock_report:
        mock_report.return_value = ("UNAVAILABLE", None)
        response = client.get("/ops/shadow-report")

    assert response.status_code == 503
    assert "Shadow report source unavailable" in response.json()["detail"]


def test_ops_shadow_report_success():
    with patch("src.liquidationheatmap.api.routers.ops._load_shadow_report") as mock_report:
        mock_report.return_value = (
            "HEALTHY",
            {"summary": {"signals_seen": 10, "accepted": 2}},
        )
        response = client.get("/ops/shadow-report")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["details"]["summary"]["accepted"] == 2


def test_ops_backfill_status_unavailable():
    response = client.get("/ops/backfill-status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UNAVAILABLE"
    assert "not configured" in data["details"]["message"]


def test_ops_evidence_spec040_latest_success(mock_evidence):
    with patch("src.liquidationheatmap.api.routers.ops._find_latest_spec040_evidence") as mock_find:
        mock_find.return_value = mock_evidence
        response = client.get("/ops/evidence/spec-040/latest")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "HEALTHY"
        assert data["details"]["verdict"] == "READY_FOR_REVIEW"
        assert data["details"]["feedback_persisted"] == 1
        assert "session_id" in data["details"]
        assert "retained_session_id" in data["details"]


def test_ops_evidence_spec040_status_mapping(mock_evidence):
    mock_evidence["gate_status"] = "BLOCKED"
    with patch("src.liquidationheatmap.api.routers.ops._find_latest_spec040_evidence") as mock_find:
        mock_find.return_value = mock_evidence
        response = client.get("/ops/evidence/spec-040/latest")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "BLOCKED"


def test_ops_evidence_spec040_malformed(mock_evidence):
    # Remove a required field
    del mock_evidence["generated_at"]
    with patch("src.liquidationheatmap.api.routers.ops._find_latest_spec040_evidence") as mock_find:
        mock_find.return_value = mock_evidence
        response = client.get("/ops/evidence/spec-040/latest")
        assert response.status_code == 503
        assert "Malformed evidence: missing 'generated_at'" in response.json()["detail"]


def test_ops_continuous_report_fail_closed():
    from fastapi import HTTPException

    with patch(
        "src.liquidationheatmap.api.routers.ops.get_continuous_report", new_callable=AsyncMock
    ) as mock_report:
        mock_report.side_effect = HTTPException(
            status_code=503, detail="Continuous report unavailable"
        )
        response = client.get("/ops/continuous-report")
        assert response.status_code == 503
        assert "Continuous report unavailable" in response.json()["detail"]


def test_ops_continuous_report_blocked_mismatch():
    with patch(
        "src.liquidationheatmap.api.routers.ops.get_continuous_report", new_callable=AsyncMock
    ) as mock_report:
        mock_report.return_value = ContinuousReport(
            session_started_at=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
            runtime_seconds=100.0,
            signals_seen=10,
            signals_accepted=5,
            orders_submitted=5,
            positions_opened=5,
            positions_closed=5,
            feedback_published=5,
            feedback_persisted=4,  # MISMATCH
            persistence_consistent=False,
            report_status="blocked",
            blocking_issues=["duckdb_reconciliation_mismatch"],
        )
        response = client.get("/ops/continuous-report")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "BLOCKED"
        assert data["details"]["report_status"] == "blocked"
        assert "duckdb_reconciliation_mismatch" in data["details"]["blocking_issues"]


def test_ops_continuous_report_blocks_on_residual_exposure():
    with patch(
        "src.liquidationheatmap.api.routers.ops.get_continuous_report", new_callable=AsyncMock
    ) as mock_report:
        mock_report.return_value = ContinuousReport(
            session_started_at=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
            runtime_seconds=100.0,
            signals_seen=4,
            signals_accepted=4,
            orders_submitted=4,
            positions_opened=2,
            positions_closed=1,
            feedback_published=0,
            feedback_persisted=0,
            persistence_consistent=True,
            report_status="blocked",
            blocking_issues=["residual_open_positions:1", "residual_open_orders:2"],
            residual_open_positions=1,
            residual_open_orders=2,
        )
        response = client.get("/ops/continuous-report")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "BLOCKED"
        assert data["details"]["residual_open_positions"] == 1
        assert data["details"]["residual_open_orders"] == 2


def test_ops_summary_degraded_when_redis_disconnected(mock_evidence):
    with patch(
        "src.liquidationheatmap.api.routers.ops.get_signal_status", new_callable=AsyncMock
    ) as mock_status:
        mock_status.return_value = SignalStatus(
            connected=False,
            last_publish="2025-12-28T10:30:00Z",
            signals_published_24h=96,
            feedback_received_24h=12,
        )
        with patch(
            "src.liquidationheatmap.api.routers.ops.get_continuous_report", new_callable=AsyncMock
        ) as mock_report:
            mock_report.return_value = ContinuousReport(
                session_started_at=datetime.now(timezone.utc),
                timestamp=datetime.now(timezone.utc),
                runtime_seconds=100.0,
                signals_seen=10,
                signals_accepted=5,
                orders_submitted=5,
                positions_opened=5,
                positions_closed=5,
                feedback_published=5,
                feedback_persisted=5,
                report_status="ok",
                blocking_issues=[],
            )
            with patch(
                "src.liquidationheatmap.api.routers.ops._find_latest_spec040_evidence"
            ) as mock_find:
                mock_find.return_value = mock_evidence
                response = client.get("/ops/summary")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "DEGRADED"
                assert data["details"]["redis"] == "UNAVAILABLE"
                assert data["details"]["signals_status_level"] == "DEGRADED"
                assert data["details"]["evidence_spec_040_latest_status"] == "HEALTHY"
