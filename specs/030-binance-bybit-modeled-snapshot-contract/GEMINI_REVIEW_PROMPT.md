# Gemini Review Prompt: spec-030

Use this file as the review handoff for implementation commits for
`specs/030-binance-bybit-modeled-snapshot-contract`.

## Copy/Paste Prompt

```text
You are reviewing implementation commits for rektslug spec-030:
Binance/Bybit Modeled Snapshot Contract.

Repository: /media/sam/1TB/rektslug
Spec files:
- specs/030-binance-bybit-modeled-snapshot-contract/spec.md
- specs/030-binance-bybit-modeled-snapshot-contract/plan.md
- specs/030-binance-bybit-modeled-snapshot-contract/tasks.md

Review target:
- Commit/range: <PASTE COMMIT SHA OR RANGE HERE>
- Slice: <PASTE SLICE NAME FROM THIS FILE HERE>

Review mode:
- Prioritize correctness, behavioral regressions, determinism, schema drift,
  missing tests, and mismatch against spec-030.
- Do not summarize the implementation first. Findings first, ordered by severity.
- Include file:line references for every finding.
- If no findings, state "No blocking findings" and list residual risks.
- Treat the spec/plan/tasks as authoritative unless they conflict with current
  audited source availability stated below.

Hard invariants:
- This is an artifact/file contract, not a live transport contract.
- `snapshot_ts` is the canonical identity timestamp and MUST be UTC ISO8601 with
  `Z` suffix in artifacts, manifests, and timestamp-derived paths.
- `run_ts` is actual generation time and MUST remain distinct from `snapshot_ts`.
- Export root is `data/validation/modeled_snapshots/{exchange}/`.
- Canonical subpaths are `artifacts/{symbol}/{snapshot_ts}/`,
  `manifests/{symbol}/`, and `batches/`.
- Manifests must be consumer-loadable with plain JSON, no rektslug Python imports.
- Availability status taxonomy is:
  `available`, `partial`, `blocked_source_unverified`,
  `blocked_source_missing`, `failed_processing`, `unsupported`.
- Binance producer must use DuckDB read-only data for deterministic exports.
  QuestDB hot data must not be used for artifact production.
- `DuckDBService.calculate_liquidations_oi_based()` is not currently
  snapshot_ts-addressable because it uses latest OI/MAX(open_time); implementation
  must pin the query/window explicitly to `snapshot_ts`.
- The aggregation bridge must not import the API router.
- Internal calculation precision must preserve Decimal/Decimal128 semantics as
  required by the project; JSON artifact interchange may serialize float64.
- Bybit readiness is per channel and per requested timestamp/window, not a
  blanket exchange state.
- Bybit `bybit_standard` requires OI, trades, funding, and klines.
- Bybit `depth_weighted` requires OI, trades, funding, klines, and orderbook.
- Bybit `depth_weighted` may be `available` only for windows covered by source
  orderbook data. It must be `blocked_*` or `partial` for uncovered gaps.
- Do not treat WebSocket/Redis as prerequisites for artifact export.

Audited Bybit source availability as of 2026-04-07:
- ccxt-data-pipeline live catalog:
  - `ohlcv/BTCUSDT-PERP.BYBIT`: 70 files, 2026-01-28 to 2026-04-07
  - `open_interest/BTCUSDT-PERP.BYBIT`: 43 files, 2026-02-24 to 2026-04-07
  - `funding_rate/BTCUSDT-PERP.BYBIT`: 43 files, 2026-02-24 to 2026-04-07
  - `trades/BTCUSDT-PERP.BYBIT`: 2 files, 2026-04-06 to 2026-04-07
  - `liquidations/BTCUSDT-PERP.BYBIT`: 2 files, 2026-04-06 to 2026-04-07
  - `orderbook/BTCUSDT-PERP.BYBIT`: 2 files, 2,449,049 rows,
    2026-04-06T14:59:54Z to 2026-04-07T16:26:49Z
- 3TB-WDC bybit_data_downloader:
  - trades BTCUSDT: 2167 files, 2020-05-01 to 2026-04-06
  - orderbook BTCUSDT: 598 files, 2024-01-01 to 2025-08-20
  - klines BTCUSDT: 6501 files, 2020-05-01 to 2026-04-06
  - funding rates: 332 total files, 166 BTCUSDT
  - open interest: 336 total files, 169 BTCUSDT
- Important gap: Bybit orderbook is not continuous between 2025-08-21 and
  live ccxt-data-pipeline coverage starting 2026-04-06. Review implementations
  must not claim `depth_weighted` availability for that uncovered interval.

Expected output format:
1. Findings
   - Severity, file:line, issue, why it matters, suggested fix.
2. Residual risks
   - Only include if no blocking finding or if a risk remains after findings.
3. Slice verdict
   - PASS / PASS WITH RISKS / BLOCKED.
```

## Review Slices

Review commits in these slices when possible. If one commit spans multiple
slices, review against all affected slices.

### Slice 0: Contract Lock-In

Tasks: T001-T004

Review focus:
- Minimum schema and manifest shape are frozen before implementation.
- Availability statuses match the shared taxonomy exactly.
- Timestamp semantics distinguish `snapshot_ts` from `run_ts`.
- Transport boundary remains artifact-first; no WebSocket/Redis dependency is
  introduced.

Typical files:
- `specs/030-binance-bybit-modeled-snapshot-contract/spec.md`
- `specs/030-binance-bybit-modeled-snapshot-contract/plan.md`
- `specs/030-binance-bybit-modeled-snapshot-contract/tasks.md`

Blockers:
- New statuses not in the taxonomy without spec update.
- Artifact production coupled to live transport.
- `snapshot_ts` and `run_ts` conflated.

### Slice 1: Shared Schema And Export Layout

Tasks: T009R, T010R, T010A, T011, T012

Review focus:
- Generic modeled snapshot schema is separate from Hyperliquid expert semantics.
- `exchange` and `model_id` are required fields.
- `research_policy_tag` is not carried into modeled exchange artifacts.
- Reused helpers such as `BucketGrid` and timestamp validation keep contract
  behavior from spec-029 where appropriate.
- Export layout writes artifacts/manifests/batches in canonical paths.
- JSON artifacts/manifests are readable without repo imports.

Likely files:
- `src/liquidationheatmap/contracts/`
- `src/liquidationheatmap/modeled_snapshots/`
- `tests/`

Blockers:
- Manifest path guessing required by consumers.
- Missing `exchange`, `model_id`, `snapshot_ts`, `source_metadata`, or
  `generation_metadata`.
- Paths derived from `run_ts` instead of `snapshot_ts`.

### Slice 2: Aggregation Bridge

Tasks: T012A

Review focus:
- Aggregation bridge converts `List[LiquidationLevel]` plus `bin_size` into
  `(BucketGrid, long_distribution, short_distribution)`.
- Bridge does not import `src/liquidationheatmap/api/routers/liquidations.py`.
- Behavior matches legacy `_aggregate_legacy_levels()` where required.
- Empty input handling is explicit and schema-valid.

Likely files:
- `src/liquidationheatmap/contracts/aggregation.py`
- `tests/`

Blockers:
- API router dependency.
- Side inversion between long and short.
- Bucket price formatting incompatible with `BucketGrid`.

### Slice 3: Binance Standard Producer

Tasks: T005-T008, T013 first channel, T014, T015A

Review focus:
- Producer uses DuckDB read-only source, not QuestDB.
- Existing Binance model/runtime is wrapped, not reimplemented unnecessarily.
- Authoritative inputs are documented: trades/aggTrades, OI, funding, klines,
  derived caches if used.
- Missing required source input yields manifest `partial` or relevant blocked
  status, not silent success.
- Input identity includes paths, time anchors, and immutable digest or retained
  manifest id per authoritative input set.

Likely files:
- `src/liquidationheatmap/ingestion/db_service.py`
- `src/liquidationheatmap/models/binance_standard.py`
- `src/liquidationheatmap/modeled_snapshots/`
- `tests/`

Blockers:
- QuestDB used for artifact export.
- Missing input produces empty/available artifact.
- No immutable source identity.

### Slice 4: Binance `depth_weighted`

Tasks: T006, T013 second channel

Review focus:
- Reads orderbook Parquet from ccxt-data-pipeline or a declared source.
- Uses actual orderbook depth to weight liquidation cluster probability.
- Keeps the channel genuinely distinct from `binance_standard`; parameter tweaks
  alone do not satisfy the spec.
- Uses the shared aggregation bridge and same artifact/manifest layout.

Likely files:
- `src/liquidationheatmap/modeled_snapshots/`
- `src/liquidationheatmap/models/`
- `tests/`

Blockers:
- `depth_weighted` is just an alias or minor parameter variant of standard.
- Orderbook availability not represented in source metadata.
- No test proving depth changes the output.

### Slice 5: Deterministic Backfill

Tasks: T015, T016, T016A

Review focus:
- Backfill records include interval, timeline policy, coverage, gaps, failures,
  and input identities.
- Same bounded backfill plus identical inputs yields stable artifacts/manifests
  except declared generation metadata.
- `snapshot_ts` pins source query windows; no latest-data drift.
- Performance gates are measured or explicitly reported.

Likely files:
- `src/liquidationheatmap/modeled_snapshots/backfill.py`
- `tests/`
- `scripts/`

Blockers:
- Query uses latest OI/MAX(open_time) without `snapshot_ts` pinning.
- Missing timestamps are discoverable only by absent files.
- Batch records omit input identity.

### Slice 6: Bybit Readiness Gate

Tasks: T017-T022

Review focus:
- Readiness is channel-specific and window-specific.
- `bybit_standard` checks OI, trades, funding, and klines.
- `depth_weighted` checks all standard inputs plus orderbook.
- Readiness report is machine-readable and includes failing input class, path,
  coverage interval, row/file counts or equivalent evidence.
- Implementation uses the audited path contracts:
  - `/media/sam/1TB/ccxt-data-pipeline/data/catalog/{type}/BTCUSDT-PERP.BYBIT/`
  - `/media/sam/3TB-WDC/bybit_data_downloader/data/historical/{type}/contract/BTCUSDT/`
  - `/media/sam/3TB-WDC/bybit_data_downloader/data/market_metrics/{type}/`

Blockers:
- Blanket `bybit_available = true`.
- `depth_weighted` marked available for 2025-08-21 to 2026-04-05 orderbook gap.
- `bybit_standard` omits klines.
- Readiness report only logs text and is not machine-readable.

### Slice 7: Bybit Blocked Manifest

Tasks: T023R, T024

Review focus:
- Blocked output is manifest-only when source readiness fails.
- No empty or fake artifact is written.
- Manifest includes `availability_status` and machine-readable reason.
- Paths remain manifest-first even for blocked channels.

Blockers:
- Consumer must inspect logs to know why Bybit is blocked.
- `available` manifest is written with missing source identities.
- Blocked manifest omits model channel.

### Slice 8: Bybit Artifact Export

Tasks: T025R, T026, T027

Review focus:
- Artifact export occurs only after readiness gate passes for the requested
  channel and window.
- `bybit_standard` uses Bybit-specific MMR tiers or an explicitly parameterized
  shared model with Bybit tier table.
- `depth_weighted` requires orderbook and respects the coverage gap.
- Input identity covers both ccxt-data-pipeline catalog and 3TB-WDC historical
  sources when used.
- Backfill records expose per-channel coverage, gaps, failures, and provenance.

Blockers:
- Binance MMR tiers reused silently for Bybit.
- Artifacts generated from uncovered orderbook windows.
- Mixed source windows without explicit provenance.

### Slice 9: Consumer Handoff Samples

Tasks: T028-T030

Review focus:
- Sample Binance export exists and is parseable by manifest path only.
- Sample Bybit manifest reflects true readiness for its requested timestamp/window.
- Documentation tells consumers to use file pickup / manifest parsing first.
- REST/WebSocket/Redis are documented as optional integration layers outside
  spec-030.

Blockers:
- Sample manifest hardcodes local absolute paths in a way consumers cannot move.
- Sample Bybit manifest says available for an uncovered window.
- Docs imply live transport is required for artifact production.

## Suggested Commit Boundaries

Use these as commit slices when practical:

1. `spec-030 contract schema/layout tests`
2. `spec-030 modeled snapshot schema helpers`
3. `spec-030 aggregation bridge`
4. `spec-030 binance standard producer`
5. `spec-030 binance depth-weighted producer`
6. `spec-030 deterministic backfill`
7. `spec-030 bybit readiness report`
8. `spec-030 bybit blocked manifest`
9. `spec-030 bybit standard export`
10. `spec-030 bybit depth-weighted export`
11. `spec-030 sample exports and consumer docs`

Each commit should include RED/GREEN tests where the task list requests TDD.

## Minimal Review Commands

Use targeted tests based on the slice. Examples:

```bash
pytest -q tests/test_modeled_snapshot_schema.py
pytest -q tests/test_modeled_snapshot_export_layout.py
pytest -q tests/test_modeled_snapshot_aggregation.py
pytest -q tests/test_binance_modeled_snapshot_producer.py
pytest -q tests/test_bybit_source_readiness.py
pytest -q tests/test_bybit_modeled_snapshot_producer.py
```

If test names differ, find relevant tests with:

```bash
rg -n "ModeledSnapshot|modeled_snapshot|bybit.*readiness|depth_weighted|input_identity" tests src
```

