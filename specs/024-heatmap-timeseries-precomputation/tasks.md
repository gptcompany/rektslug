# Tasks: Heatmap Timeseries Pre-computation Pipeline

**Input**: `specs/024-heatmap-timeseries-precomputation/spec.md`
**Dependencies**: existing heatmap-timeseries endpoint, db_service
**Feature Type**: Backend pipeline + API wiring
**Status**: COMPLETED (2026-03-19)

## Phase 1: Schema & Cache Table

- [x] T001 Add `ensure_heatmap_ts_cache_table()` to db_service (CREATE TABLE IF NOT EXISTS)
- [x] T002 Add `get_cached_ts_snapshot(symbol, interval, start_ts, end_ts, bin_size)` method
- [x] T003 Add `put_cached_ts_snapshot(symbol, interval, timestamp, bin_size, payload)` method
- [x] T004 Add unit tests for cache CRUD operations

**Checkpoint**: Cache table can store and retrieve snapshots. DONE

## Phase 2: Pre-computation Script

- [x] T005 Create `scripts/precompute_heatmap_timeseries.py` with CLI (--symbol, --interval, --days)
- [x] T006 Implement incremental logic: find last cached timestamp, compute missing ones via existing `get_heatmap_timeseries()`
- [x] T007 Implement batch insert of computed snapshots
- [x] T008 Implement retention cleanup (30d for 15m, 90d for 1h)
- [x] T009 Respect DuckDB lock via `.ingestion_lock` file check
- [x] T010 Add `SET memory_limit='1GB'` to pipeline DuckDB connection
- [x] T011 Add unit tests for pipeline logic

**Checkpoint**: Script can compute and store missing snapshots incrementally. DONE

## Phase 3: Wire API to Cache

- [x] T012 Modify `get_heatmap_timeseries()` to check cache first for default params
- [x] T013 Add staleness check: discard cached entries where `computed_at` > 2x interval age
- [x] T014 Add `X-Heatmap-Source: cache|live|memory` response header
- [x] T015 Custom `price_bin_size` or `leverage_weights` bypass cache (on-the-fly)
- [x] T016 Add integration test: cache hit returns same data as live computation

**Checkpoint**: API uses cache when available, falls back transparently. DONE

## Phase 4: Cron Integration & Performance Gates

- [x] T017 Add pre-computation step to `scripts/run-ingestion.sh` (after gap-fill)
- [x] T018 Add `/admin/precompute-heatmap` trigger endpoint for manual runs
- [x] T019 [P] Test cached API response < 200ms for standard time windows
- [x] T020 [P] Test 1 day of 15m snapshot computation < 30 seconds
- [x] T021 [P] Verify cache table size estimate < 500MB for 30d BTC+ETH
- [x] T022 Run full test suite — confirm no regressions

**Checkpoint**: Pre-computation runs automatically after ingestion. All performance gates pass. DONE

## Dependencies

```
Phase 1 (schema)
  └─> Phase 2 (script) -- uses cache table
        └─> Phase 3 (API wiring) -- reads from cache
              └─> Phase 4 (cron + perf gates)
```

T019-T021 parallel.

## Implementation Summary

### Commits
- `0d56904` feat(spec-024): heatmap timeseries pre-computation pipeline (1055 LOC)
- `3edf24f` fix(spec-024): address Codex review — 4 critical issues
- `0888aec` fix(spec-024): key watermark by price_bin_size, reject partial cache
- `c988884` fix strict heatmap cache window coverage

### Files Modified/Created
- `src/liquidationheatmap/ingestion/db_service.py` — cache CRUD methods (T001-T003)
- `scripts/precompute_heatmap_timeseries.py` — incremental pipeline (T005-T010)
- `src/liquidationheatmap/api/routers/liquidations.py` — cache wiring + `_try_duckdb_ts_cache()` (T012-T015)
- `src/liquidationheatmap/api/routers/admin.py` — `/admin/precompute-heatmap` endpoint (T018)
- `scripts/run-ingestion.sh` — cron integration (T017)
- `tests/unit/ingestion/test_heatmap_ts_cache.py` — 11 cache tests (T004)
- `tests/unit/pipeline/test_heatmap_precompute.py` — 5 pipeline tests (T011)
- `tests/unit/api/test_liquidations_db_retry.py` — 10 API/retry tests (T016, T019)

### Test Results
- 26/26 spec-024 tests passing
- Full suite green (no regressions)
