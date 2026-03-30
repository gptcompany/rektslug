# QuestDB Hot Path Phase 1

Date: 2026-03-30

## Scope

This change removes the `DuckDB -> QuestDB` bridge on the near-real-time gap-fill path.

The hot ingestion path is now:

- `ccxt-data-pipeline Parquet -> DuckDB read_parquet(...) -> QuestDB`

DuckDB is still used in-process as a query engine for Parquet reads, but it is no longer
required as the persistent destination for hot `klines`, `open_interest`, and `funding_rate`
gap-fill data.

## What Changed

- `src/liquidationheatmap/ingestion/gap_fill.py`
  - Uses QuestDB watermarks for `klines`, `open_interest`, and `funding_rates`
  - Writes new hot rows directly into QuestDB
  - Falls back to `duckdb.connect(':memory:')` if the historical DuckDB file does not exist
- `src/liquidationheatmap/ingestion/questdb_service.py`
  - Opens ILP senders via `Sender.from_conf(...)` for compatibility with the installed QuestDB client
- `scripts/fill_gap_from_ccxt.py`
  - Updated to describe the QuestDB-first hot ingestion flow
- `scripts/run-ccxt-gap-fill.sh`
  - Removed the obsolete local DuckDB write-access check from the CLI fallback path

## What This Does Not Change

- DuckDB is still present in the repo for analytics, caches, and several legacy/derived flows
- API/admin ingestion locks still exist because other runtime paths still coordinate around DuckDB
- Legacy scripts that write raw history into DuckDB are still present and need follow-up migration or deprecation

## Verification

Verified with:

- `uv run pytest -q tests/test_ingestion/test_questdb_service.py tests/test_ingestion/test_gap_fill_unit.py tests/integration/test_gap_fill_e2e.py`

Result:

- `23 passed`

## Next Step

The next implementation step is `Phase 2`:

- move hot consumers to QuestDB-only where possible
- remove unnecessary DuckDB fallbacks from realtime API paths
- keep DuckDB focused on analytics/cache workloads instead of hot serving
