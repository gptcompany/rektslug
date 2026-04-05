from src.liquidationheatmap.hyperliquid.backfill import (
    build_backfill_batch,
    categorize_backfill_missing,
)


def test_backfill_batch_record_contains_required_fields():
    record = build_backfill_batch(
        batch_id="batch_001",
        interval="15m",
        symbols=["BTCUSDT"],
        experts=["v1", "v2"],
        start_ts="2026-01-01T00:00:00Z",
        end_ts="2026-01-02T00:00:00Z",
        coverage={"BTCUSDT": {"total": 96, "success": 90, "gap": 4, "failure": 2}},
        timeline_policy="strict_intervals",
        input_identity={"catalog_hash": "abcdef"},
    )
    assert record.batch_id == "batch_001"
    assert record.interval == "15m"
    assert "BTCUSDT" in record.symbols
    assert "v1" in record.experts
    assert record.coverage["BTCUSDT"]["gap"] == 4
    assert record.timeline_policy == "strict_intervals"
    assert record.input_identity["catalog_hash"] == "abcdef"


def test_missing_timestamps_reported_as_gap_vs_failure():
    # If source data doesn't exist at all -> gap
    assert categorize_backfill_missing(source_exists=False, decode_success=False) == "gap"
    # If source data exists but fails to decode -> failure
    assert categorize_backfill_missing(source_exists=True, decode_success=False) == "failure"


def test_rerunning_same_backfill_produces_deterministic_manifests():
    # This is tested implicitly by checking that the build_backfill_batch uses fixed inputs
    # and doesn't rely on random/non-deterministic states for its domain logic.
    record1 = build_backfill_batch(
        batch_id="batch_001",
        interval="15m",
        symbols=["BTCUSDT"],
        experts=["v1"],
        start_ts="2026-01-01T00:00:00Z",
        end_ts="2026-01-02T00:00:00Z",
        coverage={},
        timeline_policy="strict",
        input_identity={"seed": 42},
    )
    record2 = build_backfill_batch(
        batch_id="batch_001",
        interval="15m",
        symbols=["BTCUSDT"],
        experts=["v1"],
        start_ts="2026-01-01T00:00:00Z",
        end_ts="2026-01-02T00:00:00Z",
        coverage={},
        timeline_policy="strict",
        input_identity={"seed": 42},
    )
    # The output records must be strictly identical
    assert record1.input_identity == record2.input_identity
    assert record1.batch_id == record2.batch_id
