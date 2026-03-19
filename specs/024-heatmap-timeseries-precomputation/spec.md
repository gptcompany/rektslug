# Spec 024: Heatmap Timeseries Pre-computation Pipeline

## Overview

The `/liquidations/heatmap-timeseries` endpoint exists and works, but computes
everything on-the-fly from raw DuckDB data. For production use, this is too slow
for the `liq-heat-map` frontend (especially at 1m/5m intervals over 7-30 day
windows).

This spec adds a pre-computation pipeline that materializes heatmap timeseries
snapshots into a DuckDB cache table, making the API response sub-second for
standard time windows.

## Scope

### In Scope

- Design and create `heatmap_timeseries_cache` DuckDB table schema
- Implement incremental snapshot pipeline (append-only, per-interval)
- Wire the existing `/liquidations/heatmap-timeseries` endpoint to read from cache
- Fall back to on-the-fly computation when cache is cold or missing
- Add cache freshness metadata to API response
- Support BTC/USDT and ETH/USDT at 15m and 1h intervals
- Integrate with existing gap-fill / ingestion cron cycle

### Out of Scope

- Real-time WebSocket push of heatmap updates (spec-025)
- New frontend visualization work
- Intervals below 15m (1m/5m deferred until demand proven)
- Exchanges beyond Binance

## Dependencies

- Existing `heatmap-timeseries` endpoint (routers/liquidations.py)
- Existing `TimeEvolvingHeatmap` model (src/liquidationheatmap/models/)
- DuckDB ingestion pipeline and gap-fill cron

## Architectural Decision

- Cache table lives in the same DuckDB file as other tables.
- Pipeline runs as a post-gap-fill step (appends new snapshots after fresh data lands).
- Cache key: `(symbol, interval, timestamp, price_bin_size)` — unique constraint. No `leverage_weights_hash` since cache only stores default weights; custom params always bypass cache.
- The cached path only serves requests using default binning/weights. Custom `price_bin_size` or `leverage_weights` bypass cache and compute on-the-fly.
- Staleness window: cache entries with `computed_at` older than 2x interval are skipped by API (fall back to live).
- Partial cache hits (range partially covered): fall back to full on-the-fly for MVP. Optimization deferred.

## Functional Requirements

- **FR-001**: Pre-computed snapshots MUST match on-the-fly output within floating-point tolerance.
- **FR-002**: The pipeline MUST be incremental (only compute missing timestamps).
- **FR-003**: The API MUST indicate whether response came from cache or live computation.
- **FR-004**: Cache MUST NOT grow unbounded — retention policy of 30 days for 15m, 90 days for 1h.
- **FR-005**: Pipeline MUST respect DuckDB single-writer lock (use ingestion lock file).

## Performance Gates

- **PG-001**: Cached API response < 200ms for any standard time window.
- **PG-002**: Pre-computation of 1 day of 15m snapshots < 30 seconds.
- **PG-003**: Cache table size < 500MB for 30 days of BTC+ETH at 15m+1h.

## Success Criteria

- **SC-001**: `liq-heat-map` frontend loads in < 1 second with cached data.
- **SC-002**: Gap-fill cron successfully appends new snapshots without manual intervention.
- **SC-003**: No regression on existing heatmap or liq-map endpoints.
