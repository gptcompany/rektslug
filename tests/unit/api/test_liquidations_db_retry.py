import asyncio

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
