# QuestDB Hot Path Phase 2

Date: 2026-03-31

## Scope

This phase completes the transition of hot API serving paths to QuestDB, officially establishing the architectural boundary between **QuestDB (Real-time Serving)** and **DuckDB (Analytical Compute & Caching)**.

DuckDB has been fully removed from the low-latency critical path for market data and latest state lookups.

## What Changed

- `/prices/klines` (1m/5m): Serves exclusively from QuestDB. No longer falls back to DuckDB for hot intervals.
- `/liquidations/history`: Serves exclusively from QuestDB.
- `/data/date-range`: Serves exclusively from QuestDB.
- `/liquidations/heatmap` & `/liquidations/compare-models`: Use QuestDB as the primary and only source for fetching the latest price, open interest, and funding rates.
- Internal helpers (`_get_latest_oi_with_questdb`, `_get_latest_funding_with_questdb` in `liquidations.py`) no longer accept or use a DuckDB fallback.
- Added strict explicit UTC localization for all DataFrames transitioning from DuckDB to QuestDB during gap-fill.
- Expanded empty QuestDB gap-fill bootstrap to include 5m klines, open interest, and funding rates.

## Architectural Boundaries

- **QuestDB**: Single source of truth for hot, real-time data serving (`klines`, `open_interest`, `funding_rates`, `liquidations`). Handled via `QuestDBService`.
- **DuckDB**: Restricted to heavy analytical batch processing (`calculate_liquidations_oi_based`), caching pre-computed heatmap timeseries, and serving long-term historical klines (e.g., > 14 days, `15m`, `1h`, `4h`, `1d`). Handled via `DuckDBService`.

## What Remains in DuckDB

- `calculate_liquidations_oi_based`: The heavy compute engine for generating heatmap levels.
- `cache/timeseries`: Persistent caching for heatmap timeseries.
- Non-hot historical endpoints.

## Verification

- Verified with unit and integration tests across API routers, ingestion services, and gap-fill flows.
- Expected test result: `pytest tests/` passes successfully with no regressions in data serving logic.
