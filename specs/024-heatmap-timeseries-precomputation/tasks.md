# Tasks: Heatmap Timeseries Pre-computation Pipeline

**Input**: `specs/024-heatmap-timeseries-precomputation/spec.md`
**Dependencies**: existing heatmap-timeseries endpoint, db_service
**Feature Type**: Backend pipeline + API wiring

## Phase 1: Schema & Cache Table

- [ ] T001 Add `ensure_heatmap_ts_cache_table()` to db_service (CREATE TABLE IF NOT EXISTS)
- [ ] T002 Add `get_cached_ts_snapshot(symbol, interval, start_ts, end_ts, bin_size)` method
- [ ] T003 Add `put_cached_ts_snapshot(symbol, interval, timestamp, bin_size, payload)` method
- [ ] T004 Add unit tests for cache CRUD operations

**Checkpoint**: Cache table can store and retrieve snapshots.

## Phase 2: Pre-computation Script

- [ ] T005 Create `scripts/precompute_heatmap_timeseries.py` with CLI (--symbol, --interval, --days)
- [ ] T006 Implement incremental logic: find last cached timestamp, compute missing ones via existing `get_heatmap_timeseries()`
- [ ] T007 Implement batch insert of computed snapshots
- [ ] T008 Implement retention cleanup (30d for 15m, 90d for 1h)
- [ ] T009 Respect DuckDB lock via `.ingestion_lock` file check
- [ ] T010 Add `SET memory_limit='1GB'` to pipeline DuckDB connection
- [ ] T011 Add unit tests for pipeline logic

**Checkpoint**: Script can compute and store missing snapshots incrementally.

## Phase 3: Wire API to Cache

- [ ] T012 Modify `get_heatmap_timeseries()` to check cache first for default params
- [ ] T013 Add staleness check: discard cached entries where `computed_at` > 2x interval age
- [ ] T014 Add `X-Heatmap-Source: cache|live` response header
- [ ] T015 Custom `price_bin_size` or `leverage_weights` bypass cache (on-the-fly)
- [ ] T016 Add integration test: cache hit returns same data as live computation

**Checkpoint**: API uses cache when available, falls back transparently.

## Phase 4: Cron Integration & Performance Gates

- [ ] T017 Add pre-computation step to `scripts/run-ingestion.sh` (after gap-fill)
- [ ] T018 Add `/admin/precompute-heatmap` trigger endpoint for manual runs
- [ ] T019 [P] Test cached API response < 200ms for standard time windows
- [ ] T020 [P] Test 1 day of 15m snapshot computation < 30 seconds
- [ ] T021 [P] Verify cache table size estimate < 500MB for 30d BTC+ETH
- [ ] T022 Run full test suite — confirm no regressions

**Checkpoint**: Pre-computation runs automatically after ingestion. All performance gates pass.

## Dependencies

```
Phase 1 (schema)
  └─> Phase 2 (script) -- uses cache table
        └─> Phase 3 (API wiring) -- reads from cache
              └─> Phase 4 (cron + perf gates)
```

T019-T021 parallel.

## MVP Strategy

1. Phase 1-2: cache table + script (can test offline)
2. Phase 3: wire API (needs running API)
3. Phase 4: integration + perf gates (needs cron cycle)
