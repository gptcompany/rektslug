# Spec-022 Validation Results

Date: 2026-03-14

## Public-Route Backend Contract

### Endpoint

`GET /liquidations/coinank-public-map?symbol={SYMBOL}&timeframe={TF}`

- Symbols: `BTCUSDT`, `ETHUSDT`
- Timeframes: `1d`, `1w`
- Response model: `CoinankPublicMapResponse` (schema_version `1.0`)
- Source module: `src/liquidationheatmap/api/public_liqmap.py`
- Router: `src/liquidationheatmap/api/routers/liquidations.py`

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| schema_version | str | Always `"1.0"` |
| source | str | `"coinank-public-builder"` |
| symbol | str | Normalized symbol |
| timeframe | str | `"1d"` or `"1w"` |
| profile | str | `"rektslug-ank-public"` |
| current_price | float | Latest price from DuckDB OI data |
| grid | object | `{step, anchor_price, min_price, max_price}` |
| leverage_ladder | list[str] | 9 tiers: `25x` through `100x` |
| long_buckets | list | `{price_level, leverage, volume}` |
| short_buckets | list | `{price_level, leverage, volume}` |
| cumulative_long | list | `{price_level, value}` descending from left |
| cumulative_short | list | `{price_level, value}` ascending from right |
| last_data_timestamp | str | ISO 8601 UTC |
| is_stale_real_data | bool | True if data > 20min old |

### Grid Rules (Frozen)

| Symbol | Timeframe | Step | Range Envelope |
|--------|-----------|------|----------------|
| BTCUSDT | 1d | 10.0 | p05..p95, clamp 8%..12% |
| BTCUSDT | 1w | 25.0 | p02..p98, clamp 12%..18% |
| ETHUSDT | 1d | 0.5 | p05..p95, clamp 8%..12% |
| ETHUSDT | 1w | 2.0 | p02..p98, clamp 12%..18% |

### Error Behavior

On builder failure: HTTP 500 with `{"error": "<class>", "detail": "<message>"}`.
No partial HTML chart or silent legacy fallback.

### Rollback Path

Frontend can revert to legacy `/liquidations/levels` by removing the endpoint switch in `liq_map_1w.html`. Legacy endpoint remains regression-tested and functional.

## Supersedes

This spec closes the remaining backend/data-path gap identified in `spec-016`.
The legacy `/liquidations/levels` endpoint remains available (deprecated) for non-public workflows.

## Validation Results (2026-03-14)

### Performance Gates

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Builder warm response | < 2s | 0.67-0.82s | PASS |
| Manifest + score size | < 1 MB | ~8KB + ~127KB | PASS |

### Distinctness Check (T020)

| Pair | 1d buckets | 1w buckets | 1d range | 1w range | Distinct? |
|------|-----------|-----------|----------|----------|-----------|
| BTCUSDT | 1488 | 3081 | 65082-76401 | 62252-79230 | YES |
| ETHUSDT | 1170 | 1380 | 1910-2243 | 1827-2326 | YES |

Grid steps differ (10 vs 25 BTC, 0.5 vs 2.0 ETH). Range envelopes differ. Bucket counts differ.

### Data Freshness (T021)

All 4 combos return `is_stale_real_data=false` with `last_data_timestamp` within minutes.

### Visual Validation Artifacts

Screenshots and manifests stored in:
- `data/validation/liqmap/ours_binance_{symbol}_{tf}_{timestamp}.png`
- `data/validation/liqmap/coinank_binance_{symbol}_{tf}_{timestamp}.png`
- `data/validation/manifests/liqmap_binance_{symbol}_{tf}_{timestamp}.json`

### Legacy Rollback (T022b)

`/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=7` returns valid data (38 long, 30 short buckets).

## Residual Differences

1. CoinAnK screenshot captures show login overlay (no COINANK_USER/PASSWORD set); full 1:1 pixel comparison requires authenticated session.
2. `hasFullLayout=false` warning in local page state — chart renders correctly but Plotly reports incomplete layout (cosmetic, not functional).
3. Data freshness warning (>5min) during validation is expected when sync container is paused.
