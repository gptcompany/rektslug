# Plan: Spec 024 — Heatmap Timeseries Pre-computation Pipeline

## Approach

Add a DuckDB cache table for pre-computed heatmap timeseries snapshots.
The existing `/liquidations/heatmap-timeseries` endpoint is wired to read
from cache first, falling back to on-the-fly computation for cache misses
or custom parameters.

## Phases

### Phase 1: Schema & Cache Table

Create `heatmap_timeseries_cache` table in DuckDB.

**Schema DDL**:
```sql
CREATE TABLE IF NOT EXISTS heatmap_timeseries_cache (
    symbol              VARCHAR NOT NULL,
    interval            VARCHAR NOT NULL,      -- '15m' or '1h'
    timestamp           TIMESTAMP NOT NULL,
    price_bin_size      DOUBLE NOT NULL,
    leverage_weights_hash VARCHAR NOT NULL,     -- SHA256 of sorted weights JSON
    payload_json        VARCHAR NOT NULL,       -- Serialized snapshot
    computed_at         TIMESTAMP DEFAULT now(),
    PRIMARY KEY (symbol, interval, timestamp, price_bin_size, leverage_weights_hash)
);
```

**Files to modify**:
- `src/liquidationheatmap/db/service.py` — add `ensure_cache_table()` and `get_cached_snapshot()` / `put_cached_snapshot()`

### Phase 2: Pre-computation Pipeline

Implement incremental snapshot computation that runs post-gap-fill.

**Files to create**:
- `src/liquidationheatmap/pipeline/heatmap_precompute.py` — main pipeline logic

**Logic**:
1. Query last cached timestamp per (symbol, interval)
2. Compute snapshots for all missing timestamps up to now
3. Batch-insert into cache table
4. Respect DuckDB lock via `.ingestion_lock` file
5. Apply retention: delete entries older than 30d (15m) / 90d (1h)

### Phase 3: Wire API to Cache

Modify the existing endpoint to check cache before computing.

**Files to modify**:
- `src/liquidationheatmap/api/routers/liquidations.py` — `get_heatmap_timeseries()`

**Logic**:
1. If request uses default `price_bin_size` and `leverage_weights` → try cache
2. Cache hit → return with `"source": "cache"` header
3. Cache miss → compute on-the-fly, return with `"source": "live"` header
4. Custom params → always compute on-the-fly (bypass cache)

### Phase 4: Cron Integration

Add pre-computation as post-gap-fill step.

**Files to modify**:
- `scripts/run-ingestion.sh` — add `uv run -m src.liquidationheatmap.pipeline.heatmap_precompute` after gap-fill
- `src/liquidationheatmap/api/routers/admin.py` — add `/admin/precompute-heatmap` trigger endpoint

### Phase 5: Tests & Performance Gates

**Files to create**:
- `tests/unit/pipeline/test_heatmap_precompute.py`
- `tests/performance/test_heatmap_cache_perf.py`

**Gates**:
- Cached response < 200ms
- 1 day of 15m snapshots computes in < 30s
- Cache table < 500MB for 30d BTC+ETH

## Dependencies

- DuckDB ingestion pipeline (existing)
- TimeEvolvingHeatmap model (existing)
- DuckDB lock file pattern (existing)

## Risk

- DuckDB single-writer lock: pre-computation must wait for gap-fill to release lock.
  Mitigation: run sequentially in same cron script, after gap-fill completes.
- Cache table growth: 30d × 96 snapshots/day × 2 symbols × 2 intervals = ~11,520 rows.
  At ~10KB/row = ~115MB. Well within 500MB budget.
