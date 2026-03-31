# QuestDB Hot Path Phase 2

Date: 2026-03-31

## Scope

This phase completes the transition of hot latest-state lookups to QuestDB, officially establishing the architectural boundary between **QuestDB (Real-time Serving)** and **DuckDB (Analytical Compute & Caching)**.

DuckDB is no longer used to resolve the latest market state on hot routes. It remains in the request path where analytical computation or historical kline source resolution is still required.

## What Changed

- `/prices/klines` (1m/5m): Serves exclusively from QuestDB. No longer falls back to DuckDB for hot intervals.
- `/liquidations/history`: Serves exclusively from QuestDB.
- `/data/date-range`: Serves exclusively from QuestDB.
- `/liquidations/heatmap`, `/liquidations/compare-models`, and `/liquidations/coinank-public-map`: Use QuestDB to resolve the latest price/open interest and, where applicable, funding rates before any DuckDB analytical compute runs.
- Internal helpers (`_get_latest_oi_with_questdb`, `_get_latest_funding_with_questdb` in `liquidations.py`) no longer accept or use a DuckDB fallback.
- Added strict explicit UTC localization for all DataFrames transitioning from DuckDB to QuestDB during gap-fill.
- Expanded empty QuestDB gap-fill bootstrap to include 5m klines, open interest, and funding rates.

## Architectural Boundaries

- **QuestDB**: Single source of truth for hot market-state lookups and real-time data serving (`klines`, `open_interest`, `funding_rates`, `liquidations`). Handled via `QuestDBService`.
- **DuckDB**: Restricted to heavy analytical batch processing (`calculate_liquidations_oi_based`), caching pre-computed heatmap timeseries, and serving historical kline coverage for analytical windows (e.g. > 14 days, `15m`, `1h`, `4h`, `1d`). Handled via `DuckDBService`.

## What Remains in DuckDB

- `calculate_liquidations_oi_based`: The heavy compute engine for generating heatmap levels.
- `cache/timeseries`: Persistent caching for heatmap timeseries.
- Non-hot historical endpoints.

## Verification

- Verified with unit and integration tests across API routers, ingestion services, and gap-fill flows.
- Expected test result: `pytest tests/` passes successfully with no regressions in data serving logic.
