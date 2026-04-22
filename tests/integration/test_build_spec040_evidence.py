from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import duckdb

from src.liquidationheatmap.signals.feedback import FeedbackDBService
from src.liquidationheatmap.signals.models import TradeFeedback


def test_build_spec040_evidence_generates_reconciled_summary(tmp_path: Path):
    db_path = tmp_path / "liquidations.duckdb"
    report_path = tmp_path / "continuous_runtime_report.json"
    output_dir = tmp_path / "evidence"

    conn = duckdb.connect(str(db_path))
    migration_sql = Path("scripts/migrations/add_signal_feedback_table.sql").read_text()
    conn.execute(migration_sql)
    conn.close()

    conn = duckdb.connect(str(db_path))
    db_service = FeedbackDBService(conn)
    session_started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    old_feedback = TradeFeedback(
        symbol="BTCUSDT",
        signal_id="before-session",
        entry_price=Decimal("94000"),
        exit_price=Decimal("94100"),
        pnl=Decimal("100"),
        timestamp=session_started_at - timedelta(hours=1),
        source="nautilus",
    )
    current_feedback = TradeFeedback(
        symbol="BTCUSDT",
        signal_id="during-session",
        entry_price=Decimal("95000"),
        exit_price=Decimal("95500"),
        pnl=Decimal("500"),
        timestamp=datetime.now(timezone.utc),
        source="nautilus",
    )
    db_service.store_feedback(old_feedback)
    db_service.store_feedback(current_feedback)
    db_service.conn.execute(
        """
        UPDATE signal_feedback
        SET created_at = ?
        WHERE signal_id = 'before-session'
        """,
        [(session_started_at - timedelta(hours=1)).replace(tzinfo=None)],
    )
    db_service.close()

    report_path.write_text(
        json.dumps(
            {
                "session_started_at": session_started_at.isoformat().replace("+00:00", "Z"),
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "runtime_seconds": 300.0,
                "signals_seen": 2,
                "signals_rejected": 0,
                "signals_accepted": 2,
                "orders_submitted": 2,
                "orders_rejected": 0,
                "orders_filled": 2,
                "positions_opened": 1,
                "positions_closed": 1,
                "feedback_published": 1,
                "residual_open_positions": 0,
                "residual_open_orders": 0,
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/build_spec040_evidence.py",
            "--runtime-snapshot-path",
            str(report_path),
            "--db-path",
            str(db_path),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "report.md").read_text(encoding="utf-8")

    assert summary["spec_id"] == "040"
    assert summary["gate_status"] == "READY_FOR_REVIEW"
    assert summary["continuous_report"]["feedback_persisted"] == 1
    assert summary["reconciliation"]["persisted_rows_in_session"] == 1
    assert summary["reconciliation"]["report_matches_duckdb"] is True
    assert summary["reconciliation"]["blocking_issues"] == []
    assert len(summary["reconciliation"]["recent_feedback_rows"]) == 1
    assert "Spec-040 Evidence Summary" in markdown
    assert "during-session" in markdown
