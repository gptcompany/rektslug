import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.liquidationheatmap.api.routers import liquidations
from src.liquidationheatmap.ingestion.db_service import IngestionLockError


def test_is_transient_duckdb_read_lock_matches_conflicting_process_message():
    exc = IngestionLockError("Database locked by another DuckDB process. Retry shortly.")
    assert liquidations._is_transient_duckdb_read_lock(exc) is True


def test_is_transient_duckdb_read_lock_ignores_gap_fill_lock_message():
    exc = IngestionLockError("Database locked for ingestion. Try again after ingestion completes.")
    assert liquidations._is_transient_duckdb_read_lock(exc) is False


def test_run_read_operation_with_retry_retries_transient_lock(monkeypatch):
    sleep_calls = []
    attempts = {"count": 0}

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    def operation():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise IngestionLockError("Database locked by another DuckDB process. Retry shortly.")
        return "ok"

    monkeypatch.setattr(liquidations.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        liquidations._run_read_operation_with_retry(
            operation,
            attempts=3,
            delay_seconds=0.01,
        )
    )

    assert result == "ok"
    assert attempts["count"] == 2
    assert sleep_calls == [0.01]


def test_run_read_operation_with_retry_does_not_retry_ingestion_lock(monkeypatch):
    sleep_calls = []
    attempts = {"count": 0}

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    def operation():
        attempts["count"] += 1
        raise IngestionLockError("Database locked for ingestion. Try again after ingestion completes.")

    monkeypatch.setattr(liquidations.asyncio, "sleep", fake_sleep)

    with pytest.raises(IngestionLockError, match="ingestion"):
        asyncio.run(
            liquidations._run_read_operation_with_retry(
                operation,
                attempts=3,
                delay_seconds=0.01,
            )
        )

    assert attempts["count"] == 1
    assert sleep_calls == []


def test_run_read_operation_with_retry_raises_after_last_transient_attempt(monkeypatch):
    sleep_calls = []
    attempts = {"count": 0}

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    def operation():
        attempts["count"] += 1
        raise IngestionLockError("Database locked by another DuckDB process. Retry shortly.")

    monkeypatch.setattr(liquidations.asyncio, "sleep", fake_sleep)

    with pytest.raises(IngestionLockError, match="Retry shortly"):
        asyncio.run(
            liquidations._run_read_operation_with_retry(
                operation,
                attempts=2,
                delay_seconds=0.01,
            )
        )

    assert attempts["count"] == 2
    assert sleep_calls == [0.01]


def test_run_read_operation_with_retry_converts_exhausted_transient_lock_to_http_500(monkeypatch):
    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    def operation():
        raise IngestionLockError("Database locked by another DuckDB process. Retry shortly.")

    monkeypatch.setattr(liquidations.asyncio, "sleep", fake_sleep)

    with pytest.raises(liquidations.HTTPException) as exc_info:
        asyncio.run(
            liquidations._run_read_operation_with_retry(
                operation,
                attempts=2,
                delay_seconds=0.01,
                exhausted_status_detail="Temporary database contention while loading heatmap timeseries.",
            )
        )

    assert exc_info.value.status_code == 500
    assert "Temporary database contention" in exc_info.value.detail
    assert sleep_calls == [0.01]


def test_synthetic_legacy_levels_keep_longs_below_price_and_shorts_above():
    long_liqs, short_liqs = liquidations._build_legacy_level_lists_from_model(
        symbol="BTCUSDT",
        model_name="binance_standard",
        current_price=70000.0,
        bin_size=1000.0,
    )

    assert len(long_liqs) >= 3
    assert len(short_liqs) >= 3
    assert all(float(entry["price_level"]) < 70000.0 for entry in long_liqs)
    assert all(float(entry["price_level"]) > 70000.0 for entry in short_liqs)
    assert {entry["leverage"] for entry in long_liqs + short_liqs} >= {
        "5x",
        "10x",
        "25x",
    }


def _cached_ts_row(ts: datetime, *, computed_at: datetime | None = None) -> dict:
    if computed_at is None:
        computed_at = datetime.now(timezone.utc)
    payload = {
        "timestamp": ts.isoformat(),
        "levels": [],
        "meta": {
            "positions_created": 0,
            "positions_consumed": 0,
            "total_long_volume": 0,
            "total_short_volume": 0,
        },
    }
    return {
        "timestamp": ts,
        "payload_json": json.dumps(payload),
        "computed_at": computed_at,
    }


def test_try_duckdb_ts_cache_rejects_missing_leading_window(monkeypatch):
    start_dt = datetime(2026, 3, 19, 0, 0, tzinfo=timezone.utc)
    rows = [
        _cached_ts_row(start_dt + timedelta(minutes=15 * step))
        for step in range(1, 7)
    ]

    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_db
    mock_db.__exit__.return_value = False
    mock_db.get_cached_ts_snapshots.return_value = rows
    monkeypatch.setattr(liquidations, "DuckDBService", MagicMock(return_value=mock_db))

    result = liquidations._try_duckdb_ts_cache(
        symbol="BTCUSDT",
        interval="15m",
        start_ts=start_dt.isoformat(),
        end_ts=(start_dt + timedelta(minutes=90)).isoformat(),
        price_bin_size=100.0,
    )

    assert result is None


def test_try_duckdb_ts_cache_rejects_gap_inside_range(monkeypatch):
    start_dt = datetime(2026, 3, 19, 0, 0, tzinfo=timezone.utc)
    rows = [
        _cached_ts_row(start_dt + timedelta(minutes=0)),
        _cached_ts_row(start_dt + timedelta(minutes=15)),
        _cached_ts_row(start_dt + timedelta(minutes=45)),
        _cached_ts_row(start_dt + timedelta(minutes=60)),
    ]

    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_db
    mock_db.__exit__.return_value = False
    mock_db.get_cached_ts_snapshots.return_value = rows
    monkeypatch.setattr(liquidations, "DuckDBService", MagicMock(return_value=mock_db))

    result = liquidations._try_duckdb_ts_cache(
        symbol="BTCUSDT",
        interval="15m",
        start_ts=start_dt.isoformat(),
        end_ts=(start_dt + timedelta(minutes=60)).isoformat(),
        price_bin_size=100.0,
    )

    assert result is None


def test_try_duckdb_ts_cache_accepts_contiguous_coverage(monkeypatch):
    start_dt = datetime(2026, 3, 19, 0, 0, tzinfo=timezone.utc)
    rows = [
        _cached_ts_row(start_dt + timedelta(minutes=15 * step))
        for step in range(0, 5)
    ]

    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_db
    mock_db.__exit__.return_value = False
    mock_db.get_cached_ts_snapshots.return_value = rows
    monkeypatch.setattr(liquidations, "DuckDBService", MagicMock(return_value=mock_db))

    result = liquidations._try_duckdb_ts_cache(
        symbol="BTCUSDT",
        interval="15m",
        start_ts=start_dt.isoformat(),
        end_ts=(start_dt + timedelta(minutes=60)).isoformat(),
        price_bin_size=100.0,
    )

    assert result is not None
    assert result.meta.total_snapshots == 5
