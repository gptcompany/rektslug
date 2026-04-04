from datetime import datetime, timezone

from src.liquidationheatmap.hyperliquid.run_metadata import (
    RunKind,
    build_run_metadata,
    calculate_next_baseline,
)


def test_run_metadata_contains_required_fields():
    meta = build_run_metadata(
        run_reason=RunKind.BASELINE,
        run_ts="2026-04-03T12:00:00Z",
        last_actual_run_ts="2026-04-03T11:45:00Z",
    )
    assert meta.run_id is not None
    assert meta.run_reason == RunKind.BASELINE
    assert meta.run_ts == "2026-04-03T12:00:00Z"
    assert meta.last_actual_run_ts == "2026-04-03T11:45:00Z"
    assert meta.producer_version is not None


def test_accepted_run_kinds():
    assert RunKind.BASELINE == "baseline"
    assert RunKind.EXTRA == "extra"
    assert RunKind.MANUAL == "manual"
    assert RunKind.BACKFILL == "backfill"


def test_extra_run_reanchors_last_actual_run_ts():
    # If last baseline was 12:00:00, and we have an extra run at 12:05:00,
    # the next baseline should be calculated from 12:05:00, meaning 12:20:00 (15m cadence)
    cadence_minutes = 15
    last_actual_run_ts_dt = datetime(2026, 4, 3, 12, 5, 0, tzinfo=timezone.utc)
    next_baseline_dt = calculate_next_baseline(last_actual_run_ts_dt, cadence_minutes)

    assert next_baseline_dt == datetime(2026, 4, 3, 12, 20, 0, tzinfo=timezone.utc)


def test_run_ts_and_snapshot_ts_distinct_during_backfill():
    # Backfill run where we process an old snapshot_ts
    snapshot_ts = "2025-10-30T12:00:00Z"
    current_run_ts = "2026-04-03T12:30:00Z"

    meta = build_run_metadata(
        run_reason=RunKind.BACKFILL, run_ts=current_run_ts, last_actual_run_ts=current_run_ts
    )
    assert meta.run_ts == current_run_ts
    assert meta.run_ts != snapshot_ts
    assert meta.run_reason == "backfill"
