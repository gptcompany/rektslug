# Tasks: Heatmap Timeseries Pre-computation Pipeline

**Input**: `specs/024-heatmap-timeseries-precomputation/spec.md`
**Dependencies**: spec-022 (public builder), existing heatmap-timeseries endpoint
**Feature Type**: Backend pipeline + API wiring

## Phase 1: Schema & Cache Table

- [ ] T001 Add `ensure_heatmap_cache_table()` to DuckDB service (CREATE TABLE IF NOT EXISTS)
- [ ] T002 Add `get_cached_snapshot(symbol, interval, timestamp, bin_size, weights_hash)` method
- [ ] T003 Add `put_cached_snapshot(symbol, interval, timestamp, bin_size, weights_hash, payload)` method
- [ ] T004 Add unit tests for cache CRUD operations

**Checkpoint**: Cache table can store and retrieve snapshots.

## Phase 2: Pre-computation Pipeline

- [ ] T005 Create `src/liquidationheatmap/pipeline/heatmap_precompute.py` with main pipeline class
- [ ] T006 Implement incremental logic: find last cached timestamp, compute missing ones
- [ ] T007 Implement batch insert of computed snapshots
- [ ] T008 Implement retention cleanup (30d for 15m, 90d for 1h)
- [ ] T009 Respect DuckDB lock via `.ingestion_lock` file check
- [ ] T010 Add `SET memory_limit='1GB'` to pipeline DuckDB connection
- [ ] T011 Add unit tests for pipeline logic (mock DuckDB, verify incremental behavior)

**Checkpoint**: Pipeline can compute and store missing snapshots.

## Phase 3: Wire API to Cache

- [ ] T012 Modify `get_heatmap_timeseries()` to check cache first for default params
- [ ] T013 Add `X-Heatmap-Source: cache|live` response header
- [ ] T014 Custom `price_bin_size` or `leverage_weights` bypass cache (on-the-fly)
- [ ] T015 Add integration test: cache hit returns same data as live computation

**Checkpoint**: API uses cache when available, falls back transparently.

## Phase 4: Cron Integration

- [ ] T016 Add pre-computation step to `scripts/run-ingestion.sh` (after gap-fill)
- [ ] T017 Add `/admin/precompute-heatmap` trigger endpoint for manual runs
- [ ] T018 Add health check: cache freshness metric to `/metrics` Prometheus endpoint

**Checkpoint**: Pre-computation runs automatically after ingestion.

## Phase 5: Performance Gates

- [ ] T019 [P] Test cached API response < 200ms for standard time windows
- [ ] T020 [P] Test 1 day of 15m snapshot computation < 30 seconds
- [ ] T021 [P] Verify cache table size < 500MB for 30d BTC+ETH at 15m+1h
- [ ] T022 Run full test suite — confirm no regressions

**Checkpoint**: All performance gates pass.

## Dependencies

```
Phase 1 (schema)
  └─→ Phase 2 (pipeline) ── uses cache table
        └─→ Phase 3 (API wiring) ── reads from cache
              └─→ Phase 4 (cron) ── triggers pipeline
                    └─→ Phase 5 (perf gates)
```

T019-T021 parallel.

## MVP Strategy

1. Phase 1-2: cache table + pipeline (can test offline)
2. Phase 3: wire API (needs running API)
3. Phase 4-5: integration (needs cron cycle)
