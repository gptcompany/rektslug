# Tasks: spec-030

## Phase 1: Contract Lock-In (Design Freeze)

- [x] T001 Re-read `spec-028`, `spec-029`, `spec-012`, and the current Binance/Bybit exchange code
- [x] T002 Freeze the minimum `ModeledSnapshotArtifact` field set and manifest shape
- [x] T002B Define the shared availability status taxonomy required by FR-009 across all exchanges:
  - `available`
  - `partial` (coverage gap but enough for degraded output)
  - `blocked_source_unverified`
  - `blocked_source_missing`
  - `failed_processing`
  - `unsupported`
- [x] T003 Freeze canonical timestamp semantics:
  - `snapshot_ts`: the identity timestamp (e.g., 12:00:00Z)
  - `run_ts`: the generation wall-clock time
- [x] T004 Freeze the architecture boundary:
  - Transport remains `spec-025`
  - Artifacts remain the primary source of truth for validation
  - Redis remains optional infrastructure, not a prerequisite

## Phase 2: Binance Source Inventory And Provenance Design

- [x] T005 Audit the exact Binance inputs already available in-repo for modeled export:
  - trades / aggTrades
  - open interest
  - funding
  - klines
  - any precomputed heatmap cache inputs used by the selected model path
- [x] T006 Define the Binance model channels to export under this contract:
  - `binance_standard` (canonical): aggregate statistical — OI + aggTrades + MMR tiers — `BinanceStandardModel`
  - `depth_weighted` (LOB-aware): orderbook depth weights liquidation probability
  - The existing `binance_standard_bias`, `funding_adjusted`, `ensemble` are parameter tweaks
    of `binance_standard` (same inputs, same formula family) — not worth separate channels
  - Two genuinely different paradigms > four similar variations
  - Binance LOB data: ccxt-pipeline orderbook, 20 levels, 720k snapshots/day, Mar 2026+
- [x] T007 Define the immutable `input_identity` fields required for Binance deterministic reruns.
  Note: `DuckDBService.calculate_liquidations_oi_based()` is NOT snapshot_ts-addressable (uses MAX(open_time)).
  The producer must add explicit `snapshot_ts` time-window pinning so identical inputs produce identical outputs.
- [x] T007A Ensure each authoritative Binance source input set has at least one immutable digest, retained manifest id, or equivalent non-mutable identity reference
- [x] T008 Document which current Binance paths are authoritative inputs versus derived caches

## Phase 3: Binance Export Implementation (TDD)

- [x] T009R RED: Write failing tests for Binance artifact schema validation
- [x] T009B RED: Write failing test that verifies Decimal128 internal precision is preserved through the export path and serialized as float64 in JSON artifacts (NFR-001 boundary validation)
- [x] T010R RED: Write failing tests for Binance manifest layout and timestamp-derived paths
- [x] T010A RED: Write failing tests for canonical export subpaths:
  - `artifacts/{symbol}/{snapshot_ts}/`
  - `manifests/{symbol}/`
  - `batches/`
- [x] T011 Create a generic modeled-snapshot schema/helper module, reusing `spec-029` patterns with explicit rename mapping:
  - `ExpertSnapshotArtifact` -> `ModeledSnapshotArtifact`
  - `expert_id` -> `model_id`
  - `research_policy_tag` -> dropped (not applicable to exchange-level contracts)
  - `exchange` -> new required field (not present in spec-029)
  - Reuse `BucketGrid`, `validate_iso8601_z_timestamp`, `validate_artifact` pattern as-is
- [x] T012 Create export root and layout under `data/validation/modeled_snapshots/binance/`
- [x] T012A Extract aggregation bridge from `liquidations.py:_aggregate_legacy_levels` into `src/liquidationheatmap/contracts/aggregation.py`:
  - input: `List[LiquidationLevel]` + `bin_size`
  - output: `(BucketGrid, long_distribution: dict[str, float], short_distribution: dict[str, float])`
  - Must work for all model channels without API router dependencies
- [x] T013 Implement Binance artifact export for two model channels:
  - `binance_standard` (canonical): ✅ aggregate statistical, validates the full pipeline first
  - `depth_weighted` (LOB-aware): ✅ reads orderbook Parquet from ccxt-pipeline,
    computes depth at each liquidation level, weights cluster probability accordingly
  - Both share: aggregation bridge, export layout, manifest writing
  - Each gets its own `model_id` in the artifact and manifest
- [x] T014 Implement Binance manifest writing with explicit availability status
- [x] T015 Implement Binance backfill batch records with interval, coverage, gaps, and provenance
- [x] T015A RED: Write failing test for Binance export when one required source input is missing (edge case spec.md:L159); manifest MUST report `partial` status instead of failing silently
- [x] T016 Prove deterministic rerun behavior for identical Binance inputs apart from declared generation metadata
- [x] T016A Benchmark: verify single Binance export completes in <10s (NFR-002) and 1-week backfill in <10min (NFR-003) for an already-ingested input set

## Phase 4: Bybit Source Readiness Gate

- [x] T017 Define the mandatory input set required before Bybit can be considered export-ready.
  Known data sources (audited 2026-04-07):
  - ccxt-data-pipeline (live daemon, default exchanges include bybit):
    - OHLCV: ✅ from 2026-01-28 (Parquet, daily)
    - Open Interest: ✅ from 2026-02-24 (Parquet, daily)
    - Funding Rate: ✅ from 2026-02-24 (Parquet, daily)
    - Trades: ✅ from 2026-04-06 (Parquet, daily)
    - Liquidations: ✅ from 2026-04-06 (Parquet, daily)
    - Orderbook: ✅ from 2026-04-06 (Parquet, daily; `orderbook.50` stream truncated to 20 levels in schema)
  - bybit_data_downloader (3TB-WDC, external repo):
    - Trades: ✅ 2167 BTCUSDT files, 2020-05-01 → 2026-04-06 (csv.gz, daily)
    - Orderbook: ✅ 598 BTCUSDT files, 2024-01-01 → 2025-08-20 (zip, daily)
    - Klines: ✅ 6501 BTCUSDT files, 2020-05-01 → 2026-04-06
    - Funding rates: ✅ 332 files total, 166 BTCUSDT
    - Open Interest: ✅ 336 files total, 169 BTCUSDT
  - Caveat: there is still an uncovered orderbook gap between the 3TB-WDC
    historical range and the ccxt-data-pipeline live catalog. `depth_weighted`
    availability must be decided per requested timestamp/window.
- [x] T018 Define the readiness statuses for Bybit using the shared taxonomy from T002B:
  - `blocked_source_unverified` (spec.md FR-012 minimum)
  - `blocked_source_missing`
  - `failed_processing`
  - `unsupported`
  - `available`
- [x] T019R RED: Write failing test for Bybit readiness report shape validation (schema, required fields, machine-readable output)
- [x] T019 Produce a machine-readable readiness report shape for Bybit source audit results
- [x] T020 Audit the actual Bybit data availability across both sources:
  - ccxt-data-pipeline Parquet files for OI/funding/klines/trades/liquidations/orderbook (verified present)
  - 3TB-WDC historical trades and orderbook (verified present, but not continuous into live catalog)
  - Determine per-channel input requirements: `bybit_standard` (OI+trades+funding+klines) vs `depth_weighted` (+orderbook)
- [x] T021 Record the canonical path contract for Bybit source files:
  - ccxt-pipeline: `/media/sam/1TB/ccxt-data-pipeline/data/catalog/{type}/BTCUSDT-PERP.BYBIT/`
  - 3TB-WDC: `/media/sam/3TB-WDC/bybit_data_downloader/data/historical/{type}/contract/BTCUSDT/`
- [x] T022 Implement the readiness gate logic including the orderbook gap (2025-08-21 to 2026-04-05)
- [x] T022 Define Bybit model channels — same two-paradigm approach as Binance:
  - `bybit_standard` (canonical): aggregate statistical — OI + trades + funding + klines + Bybit MMR tiers
    - Requires: `BybitStandardModel` with Bybit-specific MMR tiers (different from Binance)
    - OR: parameterize `BinanceStandardModel` to accept per-exchange tier tables
  - `depth_weighted` (LOB-aware): orderbook depth weights liquidation probability
    - Bybit orderbook: historical 3TB-WDC files for 2024-01-01 → 2025-08-20 plus live ccxt-data-pipeline Parquet from 2026-04-06 onward
    - Readiness gate for this channel checks orderbook availability separately from `bybit_standard` and per requested timestamp/window
  - Ingestion bridge needed: ccxt-pipeline Parquet + 3TB-WDC CSV.gz → direct Parquet read

## Phase 5: Bybit Export Implementation (Gated, TDD)

- [x] T023R RED: Write failing tests for blocked Bybit export states
- [x] T024 Implement manifest-only blocked output when Bybit readiness has not passed
- [x] T025R RED: Write failing tests for real Bybit artifact export after readiness passes
- [x] T026 Implement Bybit artifact export only after source-readiness gate is green
- [x] T027 Implement Bybit backfill batch records and input-identity metadata

## Phase 6: Consumer Handoff

- [x] T028 Produce one sample Binance export batch for consumer inspection
- [x] T029 Produce one blocked or available Bybit sample manifest reflecting the true readiness state
- [x] T030 Document how NT or any other consumer should read the artifacts:
  - file pickup / manifest parsing first
  - REST / WebSocket / Redis are optional integration layers outside this spec

## Completion Notes

- Binance should land first because it already has working model/runtime code.
- Bybit is not complete merely because an adapter name exists in the repo.
- A blocked Bybit manifest is a valid and desirable interim outcome if it
  truthfully reflects current readiness.
- The goal is to expose deterministic modeled outputs, not to choose the final
  transport mechanism.
