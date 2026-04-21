from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.check_hl_backfill_batch import (
    _resolve_batch_path,
    evaluate_batch,
)


def _batch_payload(
    *,
    status: str = "completed",
    results_count: int = 1,
    success: int = 1,
    partial: int = 0,
    failure: int = 0,
    gap: int = 0,
    anchor_failures: int = 0,
    anchor_failures_total: int | None = None,
) -> dict:
    input_identity = {
        "anchor_resolution_failures": [
            {"snapshot_ts": f"2026-04-20T{idx:02d}:00:00Z", "reason": "missing"}
            for idx in range(anchor_failures)
        ]
    }
    if anchor_failures_total is not None:
        input_identity["anchor_resolution_failures_total"] = anchor_failures_total

    return {
        "batch_id": "batch",
        "coverage": {
            "BTCUSDT": {
                "success": success,
                "partial": partial,
                "failure": failure,
                "gap": gap,
                "skipped": 0,
            }
        },
        "input_identity": input_identity,
        "generation_metadata": {
            "status": status,
            "results_count": results_count,
        },
    }


def test_evaluate_batch_accepts_completed_success() -> None:
    errors = evaluate_batch(
        _batch_payload(),
        min_results=1,
        max_failures=0,
        max_partials=0,
        max_gaps=0,
        max_anchor_resolution_failures=0,
        require_completed=True,
    )

    assert errors == []


def test_evaluate_batch_rejects_running_by_default() -> None:
    errors = evaluate_batch(
        _batch_payload(status="running"),
        min_results=1,
        max_failures=0,
        max_partials=0,
        max_gaps=0,
        max_anchor_resolution_failures=None,
        require_completed=True,
    )

    assert "expected 'completed'" in errors[0]


def test_evaluate_batch_can_allow_running_for_in_progress_checks() -> None:
    errors = evaluate_batch(
        _batch_payload(status="running"),
        min_results=1,
        max_failures=0,
        max_partials=0,
        max_gaps=0,
        max_anchor_resolution_failures=None,
        require_completed=False,
    )

    assert errors == []


def test_evaluate_batch_rejects_bad_coverage_and_anchor_failures() -> None:
    errors = evaluate_batch(
        _batch_payload(partial=1, failure=2, gap=3, anchor_failures=2),
        min_results=1,
        max_failures=0,
        max_partials=0,
        max_gaps=0,
        max_anchor_resolution_failures=1,
        require_completed=True,
    )

    assert any("failure coverage=2" in error for error in errors)
    assert any("partial coverage=1" in error for error in errors)
    assert any("gap coverage=3" in error for error in errors)
    assert any("anchor_resolution_failures=2" in error for error in errors)


def test_evaluate_batch_uses_total_anchor_failure_count_when_list_is_truncated() -> None:
    errors = evaluate_batch(
        _batch_payload(anchor_failures=100, anchor_failures_total=145),
        min_results=1,
        max_failures=0,
        max_partials=0,
        max_gaps=0,
        max_anchor_resolution_failures=100,
        require_completed=True,
    )

    assert any("anchor_resolution_failures=145" in error for error in errors)


def test_evaluate_batch_rejects_legacy_truncated_anchor_failures_without_total() -> None:
    errors = evaluate_batch(
        _batch_payload(anchor_failures=100),
        min_results=1,
        max_failures=0,
        max_partials=0,
        max_gaps=0,
        max_anchor_resolution_failures=100,
        require_completed=True,
    )

    assert any("may be truncated at 100" in error for error in errors)


def test_resolve_batch_path_picks_latest_batch(tmp_path: Path) -> None:
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    older = batch_dir / "older.json"
    newer = batch_dir / "newer.json"
    older.write_text(json.dumps(_batch_payload()), encoding="utf-8")
    newer.write_text(json.dumps(_batch_payload()), encoding="utf-8")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    assert _resolve_batch_path(batch_path=None, output_dir=tmp_path, batch_id=None) == newer
