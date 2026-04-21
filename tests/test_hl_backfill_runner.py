from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from scripts.backfill_hl_snapshots import (
    SnapshotJob,
    _aggregate_coverage,
    _build_batch_payload,
    _build_jobs,
    _run_snapshot_job,
    build_anchor_index,
    resolve_anchor,
)


def _touch(path: Path, ts: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    epoch = ts.timestamp()
    path.touch()
    import os

    os.utime(path, (epoch, epoch))


def test_build_anchor_index_and_resolve_anchor_by_mtime(tmp_path: Path) -> None:
    abci_root = tmp_path / "abci"
    anchor_1 = abci_root / "20260420" / "100.rmp"
    anchor_2 = abci_root / "20260420" / "200.rmp"
    anchor_3 = abci_root / "20260421" / "300.rmp"
    _touch(anchor_1, datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc))
    _touch(anchor_2, datetime(2026, 4, 20, 11, 0, tzinfo=timezone.utc))
    _touch(anchor_3, datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc))

    start_ts = datetime(2026, 4, 20, 10, 30, tzinfo=timezone.utc)
    end_ts = datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)
    anchor_index = build_anchor_index(abci_root, start_ts, end_ts)

    assert resolve_anchor(anchor_index, datetime(2026, 4, 20, 10, 45, tzinfo=timezone.utc)) == anchor_1
    assert resolve_anchor(anchor_index, datetime(2026, 4, 20, 11, 30, tzinfo=timezone.utc)) == anchor_2
    assert resolve_anchor(anchor_index, datetime(2026, 4, 21, 9, 15, tzinfo=timezone.utc)) == anchor_3


def test_build_jobs_marks_missing_anchor_slots(tmp_path: Path) -> None:
    start_ts = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    end_ts = datetime(2026, 4, 20, 11, 0, tzinfo=timezone.utc)
    jobs, skipped = _build_jobs(
        start_ts=start_ts,
        end_ts=end_ts,
        step_minutes=60,
        symbols=("BTCUSDT",),
        output_dir=tmp_path / "out",
        raw_provider_root=tmp_path / "raw",
        skip_existing=True,
        anchor_index=[],
    )

    assert jobs == []
    assert skipped[0]["reason"] == "no_anchor_at_or_before_snapshot"


def test_run_snapshot_job_skips_existing_manifests(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    for symbol in ("BTCUSDT", "ETHUSDT"):
        manifest_dir = output_dir / "manifests" / symbol
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "2026-04-20T10:00:00Z.json").write_text("{}", encoding="utf-8")

    result = _run_snapshot_job(
        SnapshotJob(
            snapshot_ts="2026-04-20T10:00:00Z",
            anchor_path="/tmp/anchor.rmp",
            symbols=("BTCUSDT", "ETHUSDT"),
            output_dir=str(output_dir),
            raw_provider_root=str(tmp_path / "raw"),
            skip_existing=True,
        )
    )

    assert result["statuses"] == {"BTCUSDT": "skipped", "ETHUSDT": "skipped"}


def test_run_snapshot_job_writes_snapshots_and_classifies_partial(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import scripts.backfill_hl_snapshots as runner

    context = SimpleNamespace(
        symbol="BTC",
        state=SimpleNamespace(users={"u": object()}),
    )

    monkeypatch.setattr(runner.precompute, "prepare_symbol_contexts", lambda *args, **kwargs: [context])
    monkeypatch.setattr(
        runner.precompute,
        "_build_public_payload",
        lambda **kwargs: {"source_anchor": kwargs["context"].symbol, "grid": {"step": 10.0, "min_price": 1.0, "max_price": 2.0}},
    )
    monkeypatch.setattr(runner.precompute, "_build_v3_payload", lambda context: None)
    monkeypatch.setattr(runner.precompute, "_build_v4_payload", lambda context: None)
    monkeypatch.setattr(runner.precompute, "_build_v5_payload", lambda context: None)
    monkeypatch.setattr(runner.precompute, "atomic_write_json", lambda payload, dest: dest.write_text("{}", encoding="utf-8"))

    def fake_produce_snapshots(**kwargs):
        return SimpleNamespace(
            experts={
                "v1": SimpleNamespace(availability_status="available"),
                "v2": SimpleNamespace(availability_status="missing"),
            }
        )

    monkeypatch.setattr(runner, "produce_snapshots", fake_produce_snapshots)

    result = _run_snapshot_job(
        SnapshotJob(
            snapshot_ts="2026-04-20T10:00:00Z",
            anchor_path="/tmp/anchor.rmp",
            symbols=("BTCUSDT",),
            output_dir=str(tmp_path / "out"),
            raw_provider_root=str(tmp_path / "raw"),
            skip_existing=False,
        )
    )

    assert result["statuses"] == {"BTCUSDT": "partial"}


def test_aggregate_coverage_counts_statuses() -> None:
    coverage = _aggregate_coverage(
        [
            {"statuses": {"BTCUSDT": "success", "ETHUSDT": "gap"}},
            {"statuses": {"BTCUSDT": "partial", "ETHUSDT": "skipped"}},
        ],
        ("BTCUSDT", "ETHUSDT"),
    )

    assert coverage["BTCUSDT"]["success"] == 1
    assert coverage["BTCUSDT"]["partial"] == 1
    assert coverage["ETHUSDT"]["gap"] == 1
    assert coverage["ETHUSDT"]["skipped"] == 1


def test_build_batch_payload_marks_running_state() -> None:
    start_ts = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    end_ts = datetime(2026, 4, 20, 11, 0, tzinfo=timezone.utc)
    started_at = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)

    payload = _build_batch_payload(
        batch_id="batch-running",
        start_ts=start_ts,
        end_ts=end_ts,
        step_minutes=60,
        workers=2,
        symbols=("BTCUSDT", "ETHUSDT"),
        abci_root=Path("/tmp/abci"),
        results=[
            {
                "snapshot_ts": "2026-04-20T10:00:00Z",
                "anchor_path": "/tmp/abci/anchor.rmp",
                "statuses": {},
            }
        ],
        skipped_without_anchor=[{"snapshot_ts": "2026-04-20T09:00:00Z", "reason": "no_anchor"}],
        status="running",
        started_at=started_at,
    )

    assert payload["generation_metadata"]["status"] == "running"
    assert payload["generation_metadata"]["results_count"] == 1
    assert payload["generation_metadata"]["run_started_at"] == "2026-04-21T12:00:00Z"
    assert "run_completed_at" not in payload["generation_metadata"]
    assert payload["input_identity"]["anchors_used"][0]["anchor_path"] == "/tmp/abci/anchor.rmp"
    assert payload["input_identity"]["requested_slots"] == 2
    assert payload["input_identity"]["anchors_used_total"] == 1
    assert payload["input_identity"]["anchor_resolution_failures_total"] == 1


def test_build_batch_payload_marks_completed_state() -> None:
    start_ts = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    end_ts = datetime(2026, 4, 20, 11, 0, tzinfo=timezone.utc)
    started_at = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)

    payload = _build_batch_payload(
        batch_id="batch-completed",
        start_ts=start_ts,
        end_ts=end_ts,
        step_minutes=60,
        workers=1,
        symbols=("BTCUSDT",),
        abci_root=Path("/tmp/abci"),
        results=[
            {
                "snapshot_ts": "2026-04-20T10:00:00Z",
                "anchor_path": "/tmp/abci/anchor.rmp",
                "statuses": {"BTCUSDT": "success"},
            }
        ],
        skipped_without_anchor=[],
        status="completed",
        started_at=started_at,
    )

    assert payload["coverage"]["BTCUSDT"]["success"] == 1
    assert payload["generation_metadata"]["status"] == "completed"
    assert payload["generation_metadata"]["results_count"] == 1
    assert payload["generation_metadata"]["error"] is None
    assert "run_completed_at" in payload["generation_metadata"]


def test_build_batch_payload_preserves_requested_slots_for_failed_partial_run() -> None:
    start_ts = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    end_ts = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
    started_at = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)

    payload = _build_batch_payload(
        batch_id="batch-failed",
        start_ts=start_ts,
        end_ts=end_ts,
        step_minutes=60,
        workers=2,
        symbols=("BTCUSDT",),
        abci_root=Path("/tmp/abci"),
        results=[
            {
                "snapshot_ts": "2026-04-20T10:00:00Z",
                "anchor_path": "/tmp/abci/anchor.rmp",
                "statuses": {"BTCUSDT": "success"},
            }
        ],
        skipped_without_anchor=[],
        status="failed",
        started_at=started_at,
        requested_slots=3,
        error="boom",
    )

    assert payload["input_identity"]["requested_slots"] == 3
    assert payload["generation_metadata"]["results_count"] == 1
    assert payload["generation_metadata"]["status"] == "failed"
    assert payload["generation_metadata"]["error"] == "boom"
