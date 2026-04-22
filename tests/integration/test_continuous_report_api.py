from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pytest
from fastapi.testclient import TestClient

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.signals.feedback import FeedbackDBService
from src.liquidationheatmap.signals.models import TradeFeedback


@pytest.fixture
def temp_runtime_paths():
    """Create temporary DuckDB and runtime report paths."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        db_path = root / "test_feedback.duckdb"
        report_path = root / "continuous_runtime_report.json"

        conn = duckdb.connect(str(db_path))
        migration_sql = Path("scripts/migrations/add_signal_feedback_table.sql").read_text()
        conn.execute(migration_sql)
        conn.close()

        yield db_path, report_path


def test_continuous_report_returns_session_scoped_measured_values(
    temp_runtime_paths, monkeypatch
):
    """The API should merge runtime counters with DuckDB writes for the same session."""
    db_path, report_path = temp_runtime_paths
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(db_path))
    monkeypatch.setenv("HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH", str(report_path))

    session_started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    report_path.write_text(
        (
            "{"
            f"\"session_started_at\":\"{session_started_at.isoformat().replace('+00:00', 'Z')}\","
            "\"timestamp\":\"2026-04-22T15:30:00Z\","
            "\"runtime_seconds\":300.0,"
            "\"signals_seen\":12,"
            "\"signals_rejected\":2,"
            "\"signals_accepted\":10,"
            "\"orders_submitted\":10,"
            "\"orders_rejected\":1,"
            "\"orders_filled\":9,"
            "\"positions_opened\":9,"
            "\"positions_closed\":8,"
            "\"feedback_published\":1,"
            "\"residual_open_positions\":1,"
            "\"residual_open_orders\":0"
            "}"
        ),
        encoding="utf-8",
    )

    db_service = FeedbackDBService()
    old_feedback = TradeFeedback(
        symbol="BTCUSDT",
        signal_id="before_session",
        entry_price=Decimal("90000"),
        exit_price=Decimal("90100"),
        pnl=Decimal("100"),
        timestamp=session_started_at - timedelta(hours=1),
        source="nautilus",
    )
    current_feedback = TradeFeedback(
        symbol="BTCUSDT",
        signal_id="during_session",
        entry_price=Decimal("95000"),
        exit_price=Decimal("95500"),
        pnl=Decimal("500"),
        source="nautilus",
    )
    assert db_service.store_feedback(old_feedback) is True
    assert db_service.store_feedback(current_feedback) is True
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        UPDATE signal_feedback
        SET created_at = ?
        WHERE signal_id = 'before_session'
        """,
        [(session_started_at - timedelta(hours=1)).replace(tzinfo=None)],
    )
    conn.close()
    db_service.close()

    client = TestClient(app)
    response = client.get("/signals/continuous-report")

    assert response.status_code == 200
    data = response.json()
    assert data["session_started_at"] == session_started_at.isoformat().replace("+00:00", "Z")
    assert data["signals_seen"] == 12
    assert data["orders_submitted"] == 10
    assert data["feedback_published"] == 1
    assert data["feedback_persisted"] == 1
    assert data["persistence_consistent"] is True
    assert data["report_status"] == "ok"
    assert data["blocking_issues"] == []


def test_continuous_report_returns_503_when_runtime_snapshot_missing(
    temp_runtime_paths, monkeypatch
):
    """The API must fail closed when the execution runtime snapshot is unavailable."""
    db_path, report_path = temp_runtime_paths
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(db_path))
    monkeypatch.setenv("HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH", str(report_path))

    client = TestClient(app)
    response = client.get("/signals/continuous-report")

    assert response.status_code == 503
    assert "continuous runtime report missing" in response.json()["detail"]


def test_continuous_report_returns_503_when_duckdb_unavailable(
    temp_runtime_paths, monkeypatch
):
    """T024: DuckDB-unavailable behavior fails closed (returns 503)."""
    db_path, report_path = temp_runtime_paths
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(db_path))
    monkeypatch.setenv("HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH", str(report_path))

    # Write a valid snapshot
    session_started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    report_path.write_text(
        (
            "{"
            f"\"session_started_at\":\"{session_started_at.isoformat().replace('+00:00', 'Z')}\","
            "\"timestamp\":\"2026-04-22T15:30:00Z\","
            "\"runtime_seconds\":300.0,"
            "\"signals_seen\":12,"
            "\"signals_rejected\":2,"
            "\"signals_accepted\":10,"
            "\"orders_submitted\":10,"
            "\"orders_rejected\":1,"
            "\"orders_filled\":9,"
            "\"positions_opened\":9,"
            "\"positions_closed\":8,"
            "\"feedback_published\":8,"
            "\"residual_open_positions\":1,"
            "\"residual_open_orders\":0"
            "}"
        ),
        encoding="utf-8",
    )

    # Corrupt DuckDB file or lock it exclusively
    db_path.unlink()
    db_path.write_text("corrupted duckdb file")

    client = TestClient(app)
    response = client.get("/signals/continuous-report")

    assert response.status_code == 503
    assert "could not count persisted feedback" in response.json()["detail"]


def test_continuous_report_surfaces_publish_persist_mismatch(
    temp_runtime_paths, monkeypatch
):
    """T026: Verify feedback publish/persist mismatches are visible."""
    db_path, report_path = temp_runtime_paths
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(db_path))
    monkeypatch.setenv("HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH", str(report_path))

    session_started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    report_path.write_text(
        (
            "{"
            f"\"session_started_at\":\"{session_started_at.isoformat().replace('+00:00', 'Z')}\","
            "\"timestamp\":\"2026-04-22T15:30:00Z\","
            "\"runtime_seconds\":300.0,"
            "\"signals_seen\":10,"
            "\"signals_rejected\":0,"
            "\"signals_accepted\":10,"
            "\"orders_submitted\":10,"
            "\"orders_rejected\":0,"
            "\"orders_filled\":10,"
            "\"positions_opened\":10,"
            "\"positions_closed\":10,"
            "\"feedback_published\":10,"
            "\"residual_open_positions\":0,"
            "\"residual_open_orders\":0"
            "}"
        ),
        encoding="utf-8",
    )

    # Only persist 8 feedbacks in DuckDB, creating a mismatch (10 published vs 8 persisted)
    db_service = FeedbackDBService()
    for i in range(8):
        feedback = TradeFeedback(
            symbol="BTCUSDT",
            signal_id=f"sig_{i}",
            entry_price=Decimal("95000"),
            exit_price=Decimal("95500"),
            pnl=Decimal("500"),
            timestamp=datetime.now(timezone.utc),
            source="nautilus",
        )
        db_service.store_feedback(feedback)
    db_service.close()

    client = TestClient(app)
    response = client.get("/signals/continuous-report")

    assert response.status_code == 200
    data = response.json()
    assert data["feedback_published"] == 10
    assert data["feedback_persisted"] == 8
    assert data["persistence_consistent"] is False
    assert data["report_status"] == "blocked"
    assert any("feedback_publish_persist_mismatch" in item for item in data["blocking_issues"])
