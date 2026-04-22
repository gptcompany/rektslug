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
            "\"feedback_published\":8,"
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
    assert data["feedback_published"] == 8
    assert data["feedback_persisted"] == 1


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
