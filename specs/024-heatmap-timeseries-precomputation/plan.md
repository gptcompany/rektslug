# Plan: Spec 024 — Heatmap Timeseries Pre-computation Pipeline

## Approach

Add a DuckDB cache table for pre-computed heatmap timeseries snapshots.
The existing `/liquidations/heatmap-timeseries` endpoint is wired to read
from cache first, falling back to on-the-fly computation for cache misses
or custom parameters.

**Note**: This creates a NEW table `heatmap_timeseries_cache`, separate from
the existing `heatmap_cache` table (which stores static price/density aggregations
from `liquidation_levels`). The two serve different purposes.

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
    payload_json        VARCHAR NOT NULL,       -- Serialized snapshot
    computed_at         TIMESTAMP DEFAULT now(),
    PRIMARY KEY (symbol, interval, timestamp, price_bin_size)
);
```

**Rationale**: No `leverage_weights_hash` in PK — cache only serves default
weights. Custom `price_bin_size` or `leverage_weights` bypass cache entirely
(spec FR-004). This simplifies the schema and avoids hash computation overhead.

**Files to modify**:
- `src/liquidationheatmap/ingestion/db_service.py` — add `ensure_heatmap_ts_cache_table()`, `get_cached_ts_snapshot()`, `put_cached_ts_snapshot()`

### Phase 2: Pre-computation Script

Implement incremental snapshot computation that runs post-gap-fill.

**Files to create**:
- `scripts/precompute_heatmap_timeseries.py` — standalone script (same pattern as existing `generate_heatmap_cache.py`)

**Logic**:
1. Query last cached timestamp per (symbol, interval)
2. Call existing `get_heatmap_timeseries()` for missing timestamps
3. Batch-insert into cache table
4. Respect DuckDB lock via `.ingestion_lock` file
5. Apply retention: delete entries older than 30d (15m) / 90d (1h)
6. `SET memory_limit='1GB'` on DuckDB connection

### Phase 3: Wire API to Cache

Modify the existing endpoint to check cache before computing.

**Files to modify**:
- `src/liquidationheatmap/api/routers/liquidations.py` — `get_heatmap_timeseries()`

**Logic**:
1. If request uses default `price_bin_size` and default `leverage_weights` → try cache
2. Cache hit → check staleness (`computed_at` older than 2x interval → discard, fall back to live)
3. Fresh cache hit → return with `X-Heatmap-Source: cache` header
4. Cache miss or stale → compute on-the-fly, return with `X-Heatmap-Source: live` header
5. Custom params → always compute on-the-fly (bypass cache)
6. Partial cache hits (range partially covered) → full on-the-fly fallback for MVP

**Concurrency**: DuckDB supports concurrent reads natively (WAL mode). The pre-computation
script holds the writer lock only during batch inserts. API reads are unaffected.

### Phase 4: Cron Integration & Tests

Add pre-computation as post-gap-fill step. Validate performance gates.

**Files to modify**:
- `scripts/run-ingestion.sh` — add `uv run scripts/precompute_heatmap_timeseries.py` after gap-fill
- `src/liquidationheatmap/api/routers/admin.py` — add `/admin/precompute-heatmap` trigger endpoint

**Files to create**:
- `tests/unit/pipeline/test_heatmap_precompute.py`
- `tests/performance/test_heatmap_cache_perf.py`

**Gates**:
- Cached response < 200ms
- 1 day of 15m snapshots computes in < 30s
- Cache table < 500MB for 30d BTC+ETH

## Dependencies

- DuckDB ingestion pipeline (existing)
- `get_heatmap_timeseries()` in db_service (existing — reused as computation engine)
- DuckDB lock file pattern (existing)

## Risk

- DuckDB single-writer lock: pre-computation must wait for gap-fill to release lock.
  Mitigation: run sequentially in same cron script, after gap-fill completes.
- Cache table growth: 30d x 96 snapshots/day x 2 symbols x 2 intervals = ~11,520 rows.
  At ~10KB/row = ~115MB. Well within 500MB budget.
