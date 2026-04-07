# Gemini Implementation Prompt: spec-030

Use this file to ask Gemini to implement `spec-030`. This is intentionally
different from `GEMINI_REVIEW_PROMPT.md`: the expected behavior is to edit files,
run tests, and stop after the requested slice.

## Copy/Paste Prompt

```text
You are implementing rektslug spec-030. This is not a review task.

Repository: /media/sam/1TB/rektslug
Spec files:
- specs/030-binance-bybit-modeled-snapshot-contract/spec.md
- specs/030-binance-bybit-modeled-snapshot-contract/plan.md
- specs/030-binance-bybit-modeled-snapshot-contract/tasks.md

Implementation target:
- Slice: <PASTE ONE SLICE NAME FROM THIS FILE>
- Tasks: <PASTE TASK IDS, FOR EXAMPLE T009R-T012>

Rules:
- Edit repository files directly.
- Implement only the requested slice and then stop.
- Follow TDD for tasks marked `RED`: add the failing test first, verify it fails
  for the intended reason, then implement the minimum code to pass.
- Do not modify unrelated files.
- Do not invent a live transport dependency. spec-030 is an artifact/file
  contract, not a WebSocket/Redis delivery feature.
- Do not mark tasks complete unless the slice implementation and tests are done.
- If blocked, stop and report the exact blocker, file/path, and attempted command.
- Final response must include changed files, tests run, result, and any remaining
  risks.

Hard invariants:
- Export root: `data/validation/modeled_snapshots/{exchange}/`.
- Canonical subpaths:
  - `artifacts/{symbol}/{snapshot_ts}/`
  - `manifests/{symbol}/`
  - `batches/`
- `snapshot_ts` is canonical identity time and MUST be UTC ISO8601/RFC3339 with
  `Z` suffix in artifact bodies, manifests, and timestamp-derived paths.
- `run_ts` is actual generation time and MUST remain distinct from `snapshot_ts`.
- Artifact minimum fields:
  `exchange`, `model_id`, `symbol`, `snapshot_ts`, `reference_price`,
  `bucket_grid`, `long_distribution`, `short_distribution`, `source_metadata`,
  `generation_metadata`.
- Manifest availability statuses must be from:
  `available`, `partial`, `blocked_source_unverified`,
  `blocked_source_missing`, `failed_processing`, `unsupported`.
- Manifests and artifacts must be plain JSON-loadable by a consumer without
  importing rektslug Python code.
- Binance artifact production must use DuckDB read-only data, not QuestDB.
- Current `DuckDBService.calculate_liquidations_oi_based()` is not
  `snapshot_ts`-addressable; implementation must explicitly pin source windows
  to `snapshot_ts` before claiming determinism.
- Aggregation bridge must be independent of the API router.
- Internal precision must preserve project Decimal/Decimal128 expectations;
  exported JSON interchange may use float64.
- Bybit readiness is per channel and per requested timestamp/window.
- `bybit_standard` requires OI, trades, funding, and klines.
- `depth_weighted` requires OI, trades, funding, klines, and orderbook.
- Bybit `depth_weighted` may be `available` only for windows covered by
  producer-readable orderbook data. Current producer-readable Bybit source is
  ccxt-data-pipeline Parquet; historical 3TB-WDC files are audited but remain
  `blocked_source_unverified` until a reader/normalizer exists.

Audited Bybit source availability as of 2026-04-07:
- ccxt-data-pipeline:
  - `/media/sam/1TB/ccxt-data-pipeline/data/catalog/ohlcv/BTCUSDT-PERP.BYBIT/`
    has 70 files, 2026-01-28 to 2026-04-07.
  - `/media/sam/1TB/ccxt-data-pipeline/data/catalog/open_interest/BTCUSDT-PERP.BYBIT/`
    has 43 files, 2026-02-24 to 2026-04-07.
  - `/media/sam/1TB/ccxt-data-pipeline/data/catalog/funding_rate/BTCUSDT-PERP.BYBIT/`
    has 43 files, 2026-02-24 to 2026-04-07.
  - `/media/sam/1TB/ccxt-data-pipeline/data/catalog/trades/BTCUSDT-PERP.BYBIT/`
    has 2 files, 2026-04-06 to 2026-04-07.
  - `/media/sam/1TB/ccxt-data-pipeline/data/catalog/liquidations/BTCUSDT-PERP.BYBIT/`
    has 2 files, 2026-04-06 to 2026-04-07.
  - `/media/sam/1TB/ccxt-data-pipeline/data/catalog/orderbook/BTCUSDT-PERP.BYBIT/`
    has 2 files, 2,449,049 rows, 2026-04-06T14:59:54Z to
    2026-04-07T16:26:49Z.
- 3TB-WDC bybit_data_downloader:
  - trades BTCUSDT: 2167 files, 2020-05-01 to 2026-04-06.
  - orderbook BTCUSDT: 598 files, 2024-01-01 to 2025-08-20.
  - klines BTCUSDT: 6501 files, 2020-05-01 to 2026-04-06.
  - funding rates: 332 total files, 166 BTCUSDT.
  - open interest: 336 total files, 169 BTCUSDT.
- Important gap: Bybit orderbook is not continuous between 2025-08-21 and
  live ccxt-data-pipeline coverage starting 2026-04-06.
- Current MVP behavior: live ccxt-data-pipeline Parquet windows can be
  `available`; historical-only 3TB-WDC windows must not be marked `available`
  until normalized into producer-readable files.

Start now by implementing only the requested slice.
```

## Implementation Slices

Implement these in order unless explicitly instructed otherwise.

### Slice A: Schema And Layout Foundation

Tasks: T009R, T010R, T010A, T011, T012

Goal:
- Add tests and implementation for generic modeled snapshot schema and export
  layout.

Expected implementation:
- Add schema/helper module, likely under `src/liquidationheatmap/contracts/` or
  `src/liquidationheatmap/modeled_snapshots/`.
- Reuse the Hyperliquid pattern from:
  - `src/liquidationheatmap/hyperliquid/snapshot_schema.py`
  - `src/liquidationheatmap/hyperliquid/export_layout.py`
- Rename semantics explicitly:
  - `ExpertSnapshotArtifact` -> `ModeledSnapshotArtifact`
  - `expert_id` -> `model_id`
  - `research_policy_tag` -> dropped
  - `exchange` -> required
- Add tests for:
  - required artifact fields
  - ISO8601 Z timestamp validation
  - canonical export subpaths
  - manifest JSON loadability without importing implementation classes

Stop condition:
- Schema/layout tests pass.
- Do not implement producers yet.

Suggested tests:
```bash
pytest -q tests/test_modeled_snapshot_schema.py tests/test_modeled_snapshot_export_layout.py
```

### Slice B: Aggregation Bridge

Tasks: T012A

Goal:
- Extract reusable aggregation logic independent of the API router.

Expected implementation:
- Create `src/liquidationheatmap/contracts/aggregation.py` or equivalent.
- Convert liquidation levels plus `bin_size` into:
  `(BucketGrid, long_distribution, short_distribution)`.
- Preserve behavior compatible with `_aggregate_legacy_levels()` in
  `src/liquidationheatmap/api/routers/liquidations.py`.
- Do not import the API router from the bridge.
- Add tests for:
  - long and short bucket assignment
  - empty input
  - decimal bucket rounding
  - no API-router dependency if practical

Stop condition:
- Aggregation bridge tests pass.
- Existing API tests affected by aggregation still pass if touched.

Suggested tests:
```bash
pytest -q tests/test_modeled_snapshot_aggregation.py
pytest -q tests/unit/api/test_liquidations_questdb.py
```

### Slice C: Binance Standard Producer

Tasks: T005, T007, T007A, T008, T009B, T013 first channel, T014, T015A

Goal:
- Implement deterministic Binance `binance_standard` artifact + manifest export.

Expected implementation:
- Use DuckDB read-only source for artifact production.
- Do not use QuestDB for artifact production.
- Wrap/reuse existing Binance runtime/model rather than reimplementing the
  liquidation formula from scratch.
- Add explicit `snapshot_ts` time-window pinning. Do not use latest OI or
  `MAX(open_time)` without a bound for deterministic exports.
- Emit `source_metadata.input_identity` with source paths, time anchors, and at
  least one digest, retained manifest id, or equivalent non-mutable identity.
- Missing required source input must produce `partial` or relevant blocked status
  in the manifest, not silent success.
- Add precision boundary test: internal Decimal/Decimal128 expectations
  preserved, JSON artifact may serialize float64.

Stop condition:
- Binance `binance_standard` export can write an artifact and manifest for one
  test fixture or controlled input.
- Missing source test passes.
- Do not implement `depth_weighted` in this slice unless asked.

Suggested tests:
```bash
pytest -q tests/test_binance_modeled_snapshot_producer.py
pytest -q tests/test_modeled_snapshot_schema.py
```

### Slice D: Binance `depth_weighted`

Tasks: T006, T013 second channel

Goal:
- Add Binance `depth_weighted` channel as a genuinely LOB-aware channel.

Expected implementation:
- Read orderbook Parquet from a declared source, e.g. ccxt-data-pipeline.
- Use actual book depth to weight liquidation cluster probability.
- Prove with a test that changing depth changes output.
- Share schema, export layout, manifest writing, and aggregation bridge with
  `binance_standard`.
- Include orderbook identity/coverage in `source_metadata.input_identity`.

Stop condition:
- Tests prove `depth_weighted` is not just a parameter variant.
- Do not implement Bybit in this slice.

Suggested tests:
```bash
pytest -q tests/test_binance_depth_weighted_producer.py
```

### Slice E: Binance Backfill Determinism

Tasks: T015, T016, T016A

Goal:
- Add deterministic bounded backfill for Binance.

Expected implementation:
- Emit batch records with interval, timeline policy, coverage, gaps, failures,
  and input identities.
- Same bounded backfill with identical inputs must produce stable content apart
  from declared generation metadata.
- Performance benchmarks should be measured or recorded as skipped with a clear
  reason if the local data set is unavailable.

Stop condition:
- Determinism tests pass.
- Backfill record schema is JSON-loadable.

Suggested tests:
```bash
pytest -q tests/test_modeled_snapshot_backfill.py
pytest -q tests/test_binance_modeled_snapshot_producer.py
```

### Slice F: Bybit Readiness Gate

Tasks: T017, T018, T019R, T019, T020, T021, T022

Goal:
- Implement machine-readable Bybit readiness reporting.

Expected implementation:
- Readiness report checks per channel and per requested timestamp/window.
- `bybit_standard` checks OI, trades, funding, and klines.
- `depth_weighted` checks OI, trades, funding, klines, and orderbook.
- Report includes input class, path, exists/present status, coverage interval,
  file/row count where practical, and reason for blocked/missing/partial.
- Respect audited path contracts:
  - `/media/sam/1TB/ccxt-data-pipeline/data/catalog/{type}/BTCUSDT-PERP.BYBIT/`
  - `/media/sam/3TB-WDC/bybit_data_downloader/data/historical/{type}/contract/BTCUSDT/`
  - `/media/sam/3TB-WDC/bybit_data_downloader/data/market_metrics/{type}/`
- For `depth_weighted`, mark windows in 2025-08-21 to 2026-04-05 as
  `blocked_source_missing` or `partial`; do not mark them `available`.
- Mark historical-only 3TB-WDC windows `blocked_source_unverified` unless the
  slice also implements a real historical reader/normalizer.

Stop condition:
- Readiness tests pass for:
  - covered live window
  - historical-only window blocked as unverified unless a reader exists
  - uncovered orderbook gap window
  - missing path
- Do not implement artifact export in this slice unless asked.

Suggested tests:
```bash
pytest -q tests/test_bybit_source_readiness.py
```

### Slice G: Bybit Blocked Manifest

Tasks: T023R, T024

Goal:
- Implement manifest-only blocked output when Bybit readiness fails.

Expected implementation:
- If readiness fails, write a manifest with explicit `availability_status` and
  machine-readable reason.
- Do not write empty or fake artifacts.
- Manifest remains resolvable from canonical layout.

Stop condition:
- Blocked manifest tests pass.
- No Bybit artifact is produced for blocked windows.

Suggested tests:
```bash
pytest -q tests/test_bybit_modeled_snapshot_producer.py -k blocked
```

### Slice H: Bybit Artifact Export

Tasks: T025R, T026, T027

Goal:
- Implement real Bybit artifact export after readiness passes.

Expected implementation:
- Export only after readiness passes for the requested channel/window.
- `bybit_standard` uses Bybit-specific MMR tiers or an explicitly parameterized
  shared model with Bybit tier table.
- `depth_weighted` uses available orderbook data and respects coverage gaps.
- Input identity covers ccxt-data-pipeline and any normalized 3TB-WDC sources
  actually used.
- Backfill records expose per-channel coverage, gaps, failures, and provenance.

Stop condition:
- Bybit artifact export tests pass for an available window.
- Gap window still produces blocked/partial manifest.

Suggested tests:
```bash
pytest -q tests/test_bybit_modeled_snapshot_producer.py
pytest -q tests/test_bybit_source_readiness.py
```

### Slice I: Consumer Handoff Samples

Tasks: T028, T029, T030

Goal:
- Produce sample artifacts/manifests and consumer documentation.

Expected implementation:
- One sample Binance export batch.
- One Bybit sample manifest reflecting true readiness for its requested
  timestamp/window.
- Consumer docs explain manifest-first file pickup.
- REST/WebSocket/Redis remain optional integration layers outside spec-030.

Stop condition:
- Samples are JSON-loadable.
- Docs explain how to consume from manifest path only.

Suggested tests:
```bash
python -m json.tool <sample-manifest-path>
python -m json.tool <sample-artifact-path>
```

## Recommended First Prompt

Use this to start implementation safely:

```text
Use /media/sam/1TB/rektslug/specs/030-binance-bybit-modeled-snapshot-contract/GEMINI_IMPLEMENTATION_PROMPT.md.

Implement Slice A: Schema And Layout Foundation.
Tasks: T009R, T010R, T010A, T011, T012.

Edit files directly, follow TDD, run the relevant tests, and stop after Slice A.
Final response: changed files, tests run, pass/fail, blockers.
```
