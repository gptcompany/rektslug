"""Tests for heatmap_timeseries_cache CRUD operations (spec-024 Phase 1)."""
import json
from datetime import datetime, timezone

import duckdb
import pytest


@pytest.fixture()
def cache_db(tmp_path):
    """Create an in-memory DuckDB with heatmap_timeseries_cache table."""
    from src.liquidationheatmap.ingestion.db_service import DuckDBService

    db_path = str(tmp_path / "test.duckdb")
    DuckDBService.reset_singletons()
    db = DuckDBService(db_path=db_path, read_only=False)
    db.ensure_heatmap_ts_cache_table()
    yield db
    db.close()
    DuckDBService.reset_singletons()


class TestEnsureHeatmapTsCacheTable:
    def test_table_created(self, cache_db):
        tables = [r[0] for r in cache_db.conn.execute("SHOW TABLES").fetchall()]
        assert "heatmap_timeseries_cache" in tables

    def test_idempotent(self, cache_db):
        cache_db.ensure_heatmap_ts_cache_table()
        tables = [r[0] for r in cache_db.conn.execute("SHOW TABLES").fetchall()]
        assert tables.count("heatmap_timeseries_cache") == 1


class TestPutAndGetCachedTsSnapshots:
    def test_insert_and_retrieve(self, cache_db):
        payload = json.dumps({"price_levels": [100, 200], "volumes": [1.5, 2.5]})
        rows = [
            ("BTCUSDT", "15m", "2026-03-19 12:00:00", 100.0, payload),
            ("BTCUSDT", "15m", "2026-03-19 12:15:00", 100.0, payload),
        ]
        inserted = cache_db.put_cached_ts_snapshots(rows)
        assert inserted == 2

        result = cache_db.get_cached_ts_snapshots(
            symbol="BTCUSDT",
            interval="15m",
            start_ts="2026-03-19 12:00:00",
            end_ts="2026-03-19 12:15:00",
            price_bin_size=100.0,
        )
        assert result is not None
        assert len(result) == 2
        assert json.loads(result[0]["payload_json"]) == json.loads(payload)

    def test_returns_none_when_empty(self, cache_db):
        result = cache_db.get_cached_ts_snapshots(
            symbol="BTCUSDT",
            interval="15m",
            start_ts="2026-01-01 00:00:00",
            end_ts="2026-01-01 01:00:00",
            price_bin_size=100.0,
        )
        assert result is None

    def test_upsert_on_duplicate(self, cache_db):
        payload_v1 = json.dumps({"version": 1})
        payload_v2 = json.dumps({"version": 2})

        cache_db.put_cached_ts_snapshots([
            ("BTCUSDT", "15m", "2026-03-19 12:00:00", 100.0, payload_v1),
        ])
        cache_db.put_cached_ts_snapshots([
            ("BTCUSDT", "15m", "2026-03-19 12:00:00", 100.0, payload_v2),
        ])

        result = cache_db.get_cached_ts_snapshots(
            symbol="BTCUSDT", interval="15m",
            start_ts="2026-03-19 12:00:00", end_ts="2026-03-19 12:00:00",
            price_bin_size=100.0,
        )
        assert len(result) == 1
        assert json.loads(result[0]["payload_json"])["version"] == 2

    def test_empty_rows_returns_zero(self, cache_db):
        assert cache_db.put_cached_ts_snapshots([]) == 0

    def test_different_bin_sizes_separate(self, cache_db):
        payload = json.dumps({"data": "test"})
        cache_db.put_cached_ts_snapshots([
            ("BTCUSDT", "15m", "2026-03-19 12:00:00", 100.0, payload),
            ("BTCUSDT", "15m", "2026-03-19 12:00:00", 50.0, payload),
        ])

        result_100 = cache_db.get_cached_ts_snapshots(
            symbol="BTCUSDT", interval="15m",
            start_ts="2026-03-19 12:00:00", end_ts="2026-03-19 12:00:00",
            price_bin_size=100.0,
        )
        result_50 = cache_db.get_cached_ts_snapshots(
            symbol="BTCUSDT", interval="15m",
            start_ts="2026-03-19 12:00:00", end_ts="2026-03-19 12:00:00",
            price_bin_size=50.0,
        )
        assert len(result_100) == 1
        assert len(result_50) == 1


class TestGetLastCachedTsTimestamp:
    def test_returns_none_when_empty(self, cache_db):
        assert cache_db.get_last_cached_ts_timestamp("BTCUSDT", "15m") is None

    def test_returns_latest(self, cache_db):
        payload = json.dumps({"data": "test"})
        cache_db.put_cached_ts_snapshots([
            ("BTCUSDT", "15m", "2026-03-19 10:00:00", 100.0, payload),
            ("BTCUSDT", "15m", "2026-03-19 14:00:00", 100.0, payload),
            ("BTCUSDT", "15m", "2026-03-19 12:00:00", 100.0, payload),
        ])
        last = cache_db.get_last_cached_ts_timestamp("BTCUSDT", "15m")
        assert "2026-03-19 14:00:00" in last

    def test_filters_by_price_bin_size_when_requested(self, cache_db):
        payload = json.dumps({"data": "test"})
        cache_db.put_cached_ts_snapshots([
            ("BTCUSDT", "15m", "2026-03-19 12:00:00", 100.0, payload),
            ("BTCUSDT", "15m", "2026-03-19 14:00:00", 50.0, payload),
            ("BTCUSDT", "15m", "2026-03-19 13:00:00", 100.0, payload),
        ])

        last_100 = cache_db.get_last_cached_ts_timestamp("BTCUSDT", "15m", 100.0)
        last_50 = cache_db.get_last_cached_ts_timestamp("BTCUSDT", "15m", 50.0)

        assert "2026-03-19 13:00:00" in last_100
        assert "2026-03-19 14:00:00" in last_50


class TestDeleteStaleTsCache:
    def test_deletes_old_entries(self, cache_db):
        payload = json.dumps({"data": "test"})
        cache_db.put_cached_ts_snapshots([
            ("BTCUSDT", "15m", "2025-01-01 00:00:00", 100.0, payload),
            ("BTCUSDT", "15m", "2026-03-19 12:00:00", 100.0, payload),
        ])
        cache_db.delete_stale_ts_cache(retention_15m_days=30)

        result = cache_db.get_cached_ts_snapshots(
            symbol="BTCUSDT", interval="15m",
            start_ts="2025-01-01 00:00:00", end_ts="2026-12-31 00:00:00",
            price_bin_size=100.0,
        )
        assert len(result) == 1
        assert "2026-03-19" in str(result[0]["timestamp"])
