#!/usr/bin/env python3
"""Build the spec-040 evidence package from a continuous runtime snapshot."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.liquidationheatmap.signals.feedback import (
    ContinuousReportUnavailableError,
    FeedbackDBService,
    load_continuous_runtime_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a spec-040 evidence summary from runtime snapshot + DuckDB.",
    )
    parser.add_argument("--runtime-snapshot-path", help="Override continuous runtime snapshot path.")
    parser.add_argument("--db-path", help="Override feedback DuckDB path.")
    parser.add_argument(
        "--output-dir",
        default="specs/040-nautilus-continuous-paper-testnet/evidence",
        help="Directory where summary.json and report.md will be written.",
    )
    parser.add_argument(
        "--row-limit",
        type=int,
        default=10,
        help="Maximum number of recent feedback rows to retain in the evidence summary.",
    )
    return parser.parse_args()


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _load_session_rows(
    db_service: FeedbackDBService,
    *,
    session_started_at: datetime,
    row_limit: int,
) -> tuple[int, list[dict[str, Any]]]:
    total_result = db_service.conn.execute(
        """
        SELECT COUNT(*)
        FROM signal_feedback
        WHERE created_at >= ?
        """,
        [session_started_at.replace(tzinfo=None)],
    ).fetchone()
    total_rows = int(total_result[0] if total_result else 0)

    rows = db_service.conn.execute(
        """
        SELECT
            symbol,
            signal_id,
            CAST(entry_price AS VARCHAR),
            CAST(exit_price AS VARCHAR),
            CAST(pnl AS VARCHAR),
            timestamp,
            source,
            created_at
        FROM signal_feedback
        WHERE created_at >= ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [session_started_at.replace(tzinfo=None), row_limit],
    ).fetchall()

    recent_rows = [
        {
            "symbol": row[0],
            "signal_id": row[1],
            "entry_price": row[2],
            "exit_price": row[3],
            "pnl": row[4],
            "timestamp": _iso(row[5]),
            "source": row[6],
            "created_at": _iso(row[7]),
        }
        for row in rows
    ]
    return total_rows, recent_rows


def _build_markdown(summary: dict[str, Any]) -> str:
    report = summary["continuous_report"]
    reconciliation = summary["reconciliation"]
    lines = [
        "# Spec-040 Evidence Summary",
        "",
        f"- generated_at: `{summary['generated_at']}`",
        f"- runtime_snapshot_path: `{summary['runtime_snapshot_path']}`",
        f"- feedback_db_path: `{summary['feedback_db_path']}`",
        f"- gate_status: `{summary['gate_status']}`",
        "",
        "## Continuous Report",
        "",
        f"- session_started_at: `{report['session_started_at']}`",
        f"- timestamp: `{report['timestamp']}`",
        f"- signals_seen: `{report['signals_seen']}`",
        f"- signals_accepted: `{report['signals_accepted']}`",
        f"- orders_submitted: `{report['orders_submitted']}`",
        f"- positions_opened: `{report['positions_opened']}`",
        f"- positions_closed: `{report['positions_closed']}`",
        f"- feedback_published: `{report['feedback_published']}`",
        f"- feedback_persisted: `{report['feedback_persisted']}`",
        f"- report_status: `{report['report_status']}`",
        "",
        "## Reconciliation",
        "",
        f"- persisted_rows_in_session: `{reconciliation['persisted_rows_in_session']}`",
        f"- report_matches_duckdb: `{reconciliation['report_matches_duckdb']}`",
    ]
    if reconciliation["blocking_issues"]:
        lines.extend(
            [
                "",
                "## Blocking Issues",
                "",
                *[f"- `{issue}`" for issue in reconciliation["blocking_issues"]],
            ]
        )
    if reconciliation["recent_feedback_rows"]:
        lines.extend(["", "## Recent Feedback Rows", ""])
        for row in reconciliation["recent_feedback_rows"]:
            lines.append(
                "- "
                f"`{row['signal_id']}` {row['symbol']} pnl={row['pnl']} "
                f"created_at={row['created_at']}"
            )
    return "\n".join(lines) + "\n"


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    if args.runtime_snapshot_path:
        os.environ["HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH"] = str(
            Path(args.runtime_snapshot_path).resolve()
        )
    if args.db_path:
        db_path = str(Path(args.db_path).resolve())
        os.environ["FEEDBACK_DB_PATH"] = db_path
        os.environ["HEATMAP_DB_PATH"] = db_path

    runtime_snapshot = load_continuous_runtime_snapshot()
    db_service = FeedbackDBService()
    try:
        report = db_service.get_continuous_report(runtime_snapshot)
        session_started_at = datetime.fromisoformat(
            str(runtime_snapshot["session_started_at"]).replace("Z", "+00:00")
        )
        total_rows, recent_rows = _load_session_rows(
            db_service,
            session_started_at=session_started_at,
            row_limit=args.row_limit,
        )
    finally:
        db_service.close()

    report_payload = report.model_dump(mode="json")
    blocking_issues = list(report_payload["blocking_issues"])
    report_matches_duckdb = total_rows == int(report_payload["feedback_persisted"])
    if not report_matches_duckdb:
        blocking_issues.append(
            "duckdb_reconciliation_mismatch:"
            f" report_feedback_persisted={report_payload['feedback_persisted']}"
            f" duckdb_rows={total_rows}"
        )

    if blocking_issues:
        gate_status = "BLOCKED"
    elif (
        int(report_payload["positions_closed"]) == 0
        or int(report_payload["feedback_persisted"]) == 0
    ):
        gate_status = "PENDING_RUNTIME"
    else:
        gate_status = "READY_FOR_REVIEW"

    return {
        "spec_id": "040",
        "name": "Nautilus Continuous Paper/Testnet Runtime",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runtime_snapshot_path": str(
            Path(os.environ["HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH"]).resolve()
        ),
        "feedback_db_path": str(Path(os.environ["FEEDBACK_DB_PATH"]).resolve()),
        "gate_status": gate_status,
        "continuous_report": report_payload,
        "reconciliation": {
            "persisted_rows_in_session": total_rows,
            "report_matches_duckdb": report_matches_duckdb,
            "recent_feedback_rows": recent_rows,
            "blocking_issues": blocking_issues,
        },
    }


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        summary = build_summary(args)
    except ContinuousReportUnavailableError as exc:
        print(f"error: {exc}")
        return 1

    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report_path.write_text(_build_markdown(summary), encoding="utf-8")
    print(summary_path)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
