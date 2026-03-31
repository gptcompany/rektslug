# QuestDB Runtime Boundary Matrix

Date: 2026-03-31

## Frozen Rule

- **QuestDB** owns hot/latest market-state lookups and fully real-time serving paths.
- **DuckDB** owns analytical compute, cache lookup/persistence, and cold historical coverage.
- Any endpoint still mixing both must say so explicitly and define whether that hybrid shape is **intentional** or **temporary**.

## Endpoint Matrix

| Endpoint | Latest state source | Main data / compute path | Cache layer | Fallbacks | Boundary status | Next action |
|---|---|---|---|---|---|---|
| `GET /prices/klines?interval=1m|5m` | QuestDB | QuestDB `klines` | None | No DuckDB fallback for hot intervals; returns 404/503 on missing hot data | **QuestDB-only** | Keep as-is |
| `GET /prices/klines?interval=15m|1h|4h|1d` | QuestDB preferred | QuestDB first, then DuckDB historical tables | None | Falls back to DuckDB when QuestDB has no rows for cold intervals | **Hybrid by design** | Decide in Phase 3 whether cold intervals stay dual-source |
| `GET /data/date-range` | QuestDB | QuestDB `open_interest` range | None | 503 if QuestDB unavailable | **QuestDB-only** | Keep as-is |
| `GET /liquidations/history` | QuestDB | QuestDB `liquidations` | None | Returns empty list only on transient contention retry exhaustion | **QuestDB-only** | Keep as-is |
| `GET /liquidations/heatmap` | QuestDB | In-process model compute (`BinanceStandardModel` / `EnsembleModel`) | None | Static fallback price/open interest/funding when QuestDB unavailable | **QuestDB latest + in-process compute** | Keep latest-state on QuestDB; no DuckDB work needed here |
| `GET /liquidations/compare-models` | QuestDB | In-process model compute (`BinanceStandardModel` / `FundingAdjustedModel` / `EnsembleModel`) | None | Static fallback price/open interest/funding when QuestDB unavailable | **QuestDB latest + in-process compute** | Keep as-is |
| `GET /liquidations/levels` | Binance REST first, then QuestDB fallback | DuckDB dynamic bin sizing + DuckDB `calculate_liquidations_oi_based` | None | Falls back to model-generated legacy bins when DuckDB compute is unavailable | **Legacy hybrid** | Deprecation path or migration decision in Phase 3 |
| `GET /liquidations/coinank-public-map` | QuestDB | DuckDB `calculate_liquidations_oi_based` + DuckDB historical kline source resolution | None | Static fallback latest price if QuestDB unavailable | **Hybrid by design** | Keep if public liq-map remains analytics-backed; otherwise redesign compute path |
| `GET /liquidations/heatmap-timeseries` hot window | QuestDB for live snapshots | QuestDB live reconstruction for recent windows | In-memory cache + DuckDB precomputed cache | Falls back to DuckDB live compute when QuestDB is unavailable | **Hybrid by design** | This is the main Phase 3 architecture decision |
| `GET /liquidations/heatmap-timeseries` cold window | QuestDB for dynamic bin-size lookup only | DuckDB cache or DuckDB live compute | In-memory cache + DuckDB precomputed cache | Empty response or DuckDB fallback depending on failure mode | **DuckDB analytics path** | Keep unless timeseries is migrated further |

## Immediate Phase 3 Decisions

1. Freeze whether cold `klines` intervals remain dual-source or move behind an explicit historical-only contract.
2. Freeze whether `heatmap-timeseries` remains hybrid or gets split into a clearly hot QuestDB path and a clearly cold DuckDB path.
3. Decide whether `/liquidations/levels` is worth further migration or should remain deprecated until removal.

## Out of Scope for This Matrix

- Admin endpoints in `api/v1` that coordinate ingestion (`prepare-for-ingestion`, `refresh-connections`, `gap-fill`) are intentionally excluded from the serving boundary matrix because they manage lifecycle/coordination rather than public data serving.
- Hyperliquid sidecar routes are excluded because they are file-backed sidecar outputs, not QuestDB/DuckDB runtime paths.
