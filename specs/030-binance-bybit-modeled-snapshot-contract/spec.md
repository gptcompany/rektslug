# Feature Specification: Binance/Bybit Modeled Snapshot Contract

**Feature Branch**: `030-binance-bybit-modeled-snapshot-contract`
**Created**: 2026-04-05
**Status**: Implemented
**Input**: Reuse the `spec-028` persistence discipline and the `spec-029` producer/export contract to make Binance and Bybit consumable as deterministic modeled-snapshot producers
**Dependencies**: spec-012 (exchange aggregation baseline), spec-024 (heatmap precompute), spec-028 (consumer checkpoint discipline), spec-029 (producer contract patterns), current Binance liquidation model/runtime, external downloader/collector repo for Bybit orderbook persistence

## Context

`rektslug` already has a meaningful Binance implementation:

- ingestion and storage for market inputs
- liquidation modeling via `binance_standard`
- REST serving via `/liquidations/levels` and `/liquidations/heatmap-timeseries`
- precompute support for heatmap timeseries

What does **not** exist yet is a formal producer contract for Binance and Bybit comparable to the Hyperliquid producer/export discipline introduced in `spec-029`.

That missing layer matters for three reasons:

1. consumer systems such as NT or external evaluators should not depend on ad hoc local API calls or repo-internal glue
2. reproducible research and replay require explicit input identity, manifests, and backfill semantics
3. Bybit cannot be treated as production-ready until its source persistence path, especially orderbook persistence on the 3TB WDC volume, is proven and auditable

This spec defines a **modeled snapshot contract** for Binance and Bybit:

- `spec-028` patterns govern the source-data persistence discipline
- `spec-029` patterns govern export layout, manifesting, timestamp identity, and deterministic backfill

The result is a shared contract that lets `rektslug` expose modeled exchange snapshots as deterministic artifacts, without forcing downstream consumers to import internal model code.

## Scope

### In Scope

- Define a producer/export contract for modeled snapshots for Binance and Bybit
- Reuse existing Binance runtime/model code as the first producer implementation
- Define source-identity and persistence requirements needed for deterministic reruns
- Define explicit readiness gates for Bybit, with source persistence as a hard prerequisite
- Define artifact, manifest, and backfill layout for downstream consumers
- Keep transport separate from artifact production

### Out of Scope

- Implementing WebSocket or Redis delivery for these snapshots
- Replacing the existing REST API
- Real-time exchange aggregation changes beyond what is needed for source audit
- Inventing a new liquidation formula for Binance or Bybit in this spec
- Treating Bybit as ready before source persistence is verified
- External downloader/collector implementation details, except where this spec declares the contract that repo must satisfy

## Current State Inventory

### Binance

Implemented and reusable now:

- `src/liquidationheatmap/models/binance_standard.py`
- `src/liquidationheatmap/api/routers/liquidations.py`
- `src/liquidationheatmap/api/routers/market.py`
- `scripts/precompute_heatmap_timeseries.py`
- current ingestion stack for trades, funding, open interest, and klines

Missing:

- timestamp-addressable modeled artifacts
- manifest-driven export
- immutable input identity for deterministic backfill claims
- producer/export boundary for external consumers

### Bybit

Present but not production-ready:

- `src/exchanges/bybit.py` exists only as a stub
- `src/exchanges/aggregator.py` is aware of Bybit but skips it when unimplemented

Current state:

- source persistence for required inputs exists across ccxt-data-pipeline and 3TB-WDC
- Bybit live orderbook, trades, and liquidations are now persisted in ccxt-data-pipeline
  Parquet catalog from 2026-04-06 onward
- historical Bybit orderbook exists on 3TB-WDC for BTCUSDT from 2024-01-01 to
  2025-08-20, but there is still an uncovered historical gap before the live
  ccxt-data-pipeline catalog begins
- readiness gate validates producer-readable source availability per channel and
  requested timestamp/window before export. Current producer-readable Bybit
  artifacts use ccxt-data-pipeline Parquet; 3TB-WDC historical files are audited
  but remain `blocked_source_unverified` until a dedicated historical reader or
  normalization bridge is implemented.

## Producer / Consumer Boundary

### `rektslug` Responsibilities

- audit and declare which source inputs feed each modeled snapshot
- produce deterministic modeled artifacts for supported exchanges
- persist manifest-indexed exports and backfill batches
- expose immutable provenance and input-identity metadata
- mark unsupported or blocked channels explicitly

### Consumer Responsibilities

- consume manifests and artifacts without importing `rektslug` internals
- decide whether to use REST, WebSocket, Redis, or file pickup at integration time
- perform evaluation, ranking, trading logic, or NT-specific binding outside this spec

### Explicit Rule

This spec defines a **file/artifact contract**, not a live transport contract.

- WebSocket delivery remains the concern of `spec-025`
- Redis/pub-sub remains optional infrastructure for signals or future fan-out
- artifact production must remain useful even if no live transport exists

## User Scenarios & Testing

### User Story 1 - Binance Artifact Producer (Priority: P1)

As a consumer of Binance liquidation maps, I need `rektslug` to export deterministic modeled snapshots from the already-existing Binance engine so that downstream systems can consume them without calling local repo-specific code paths.

**Why this priority**: Binance is the shortest path because the model/runtime already exists in this repo.

**Independent Test**: Produce one Binance snapshot batch for `BTCUSDT`, validate artifact and manifest shape, rerun with identical inputs, and confirm stable outputs apart from declared generation metadata.

**Acceptance Scenarios**:

1. **Given** a supported Binance symbol and canonical timestamp, **When** export runs, **Then** a modeled artifact and manifest are written under the declared export root.
2. **Given** the same inputs and the same `snapshot_ts`, **When** export is rerun, **Then** content is deterministic apart from declared generation metadata.
3. **Given** a consumer that only knows the manifest path, **When** it resolves one Binance snapshot, **Then** it can locate the artifact and read provenance without importing `src/liquidationheatmap/`.

---

### User Story 2 - Bybit Readiness Gate (Priority: P1)

As an operator, I need Bybit to remain explicitly blocked until source persistence is verified, so that the repo does not claim support for a modeled output that lacks auditable inputs.

**Why this priority**: The current risk is false confidence, not merely missing code.

**Independent Test**: Run a readiness audit that checks whether required Bybit source inputs exist on the expected storage volume, are written with explicit paths, and can be referenced from input-identity metadata.

**Acceptance Scenarios**:

1. **Given** Bybit orderbook persistence is not proven, **When** a Bybit export is requested, **Then** the manifest reports `availability_status: "blocked_source_unverified"` instead of pretending success.
2. **Given** the source audit finds path, naming, or write failures, **When** the readiness report is generated, **Then** the root cause is machine-readable and tied to the failing input class.
3. **Given** the source audit later passes, **When** Bybit export is enabled, **Then** the artifact includes immutable input-identity references to persisted source data.

---

### User Story 3 - Shared Consumer Contract Across Exchanges (Priority: P1)

As a downstream consumer, I need Binance and Bybit to use the same modeled snapshot schema and export semantics so that integration logic does not fork on ad hoc exchange-specific layouts.

**Why this priority**: The value of this work is contract stability, not just producing more files.

**Independent Test**: Load one Binance manifest and one Bybit manifest using the same consumer parser and verify that both expose the same required top-level fields and status semantics.

**Acceptance Scenarios**:

1. **Given** a modeled snapshot from Binance and one from Bybit, **When** the consumer reads them, **Then** shared fields such as `exchange`, `model_id`, `symbol`, `snapshot_ts`, `bucket_grid`, and provenance are present in the same locations.
2. **Given** one exchange is unavailable, **When** the consumer reads its manifest, **Then** the missing or blocked state is explicit and machine-readable.
3. **Given** a bounded historical backfill, **When** the batch record is written, **Then** coverage, gaps, and input identities are explicit per exchange.

## Edge Cases

- Binance export requested for a timestamp where one required source input is missing
- Binance export requested while source inputs exist but come from mixed logic versions
- Bybit source files exist, but are written outside the expected 3TB WDC path
- Bybit downloader accepts `orderbook` in config/CLI but silently writes nothing
- backfill rerun uses different retained source files for the same `snapshot_ts`
- a transport layer exists later, but artifact schema drifts because live-serving code bypasses manifests

## Requirements

### Functional Requirements

- **FR-001**: The system MUST define a shared `ModeledSnapshotArtifact` contract for Binance and Bybit.
- **FR-002**: Every exported artifact MUST include at least `exchange`, `model_id`, `symbol`, `snapshot_ts`, `reference_price`, `bucket_grid`, `long_distribution`, `short_distribution`, `source_metadata`, and `generation_metadata`.
- **FR-003**: `snapshot_ts` MUST be the canonical identity timestamp and MUST use UTC RFC 3339 / ISO8601 format with `Z` suffix in artifact bodies, manifests, and timestamp-derived paths.
- **FR-004**: Export layout MUST be manifest-first and MUST NOT require downstream path guessing.
- **FR-005**: The export root MUST be `data/validation/modeled_snapshots/{exchange}/`.
- **FR-005A**: Under each exchange export root, the contract MUST define canonical subpaths for `artifacts/{symbol}/{snapshot_ts}/`, `manifests/{symbol}/`, and `batches/`.
- **FR-006**: Every manifest MUST declare explicit `availability_status` for the requested model channel.
- **FR-007**: Binance MUST be the first implemented exchange under this contract and MUST reuse the current Binance model/runtime rather than re-implementing it from scratch.
- **FR-008**: Binance artifacts MUST record immutable input-identity metadata sufficient to audit deterministic reruns, including source paths, time anchors, and at least one immutable digest, retained source-manifest id, or equivalent non-mutable identity reference for each authoritative source input set used by the export.
- **FR-009**: The system MUST distinguish between `available`, `partial` (degraded coverage), source availability failures, processing failures, and intentionally unsupported states.
- **FR-010**: Bybit availability status MUST be determined by the readiness gate at export time. Source data exists in ccxt-data-pipeline (OI/funding/klines from Feb 2026+, live trades/liquidations/orderbook from 2026-04-06+) and on 3TB-WDC (trades from 2020, historical orderbook from 2024). The readiness gate verifies per-channel, producer-readable input availability for the requested timestamp/window, not a blanket block. Current producer-readable Bybit inputs are ccxt-data-pipeline Parquet files; 3TB-WDC historical files are audited source candidates but MUST remain `blocked_source_unverified` until a reader/normalizer exists.
- **FR-011**: Bybit readiness MUST include explicit verification that required source inputs persist to the expected storage paths. Required inputs per model channel:
  - `bybit_standard`: Open Interest, trades, funding rate, klines
  - `depth_weighted`: all of the above PLUS orderbook snapshots
  - The readiness gate verifies these against ccxt-data-pipeline catalog and records 3TB-WDC historical paths as audited-but-not-yet-producer-readable sources. Bybit orderbook is present in 3TB-WDC historical files for BTCUSDT 2024-01-01 to 2025-08-20 and in ccxt-data-pipeline Parquet from 2026-04-06 onward; current `available` status is limited to producer-readable Parquet windows. Historical-only windows MUST remain `blocked_source_unverified`, and any requested window in the uncovered gap MUST remain `blocked_source_missing` or `partial`.
- **FR-012**: If Bybit source persistence is not verified, its manifest MUST use a blocked status such as `blocked_source_unverified` rather than returning an empty or fake artifact.
- **FR-013**: Backfill runs MUST emit batch records that declare interval, timeline policy, coverage, gaps, failures, and input identities.
- **FR-014**: Rerunning the same bounded backfill with identical inputs MUST be deterministic apart from declared generation metadata.
- **FR-015**: The contract MUST remain transport-agnostic. Artifact production MUST NOT depend on WebSocket or Redis delivery.
- **FR-016**: The spec MUST document which existing Binance inputs are already available in-repo and which Bybit inputs remain external dependencies.
- **FR-017**: The contract MUST support multiple model channels per exchange. Each exchange MUST export at least two channels with genuinely different paradigms:
  - `{exchange}_standard` (canonical): aggregate statistical model — OI + trades + funding + exchange-specific MMR tiers
  - `depth_weighted` (LOB-aware): uses orderbook depth to weight liquidation cluster probability (thin book = cascade more likely)
  - Both Binance and Bybit MUST implement both channels. The `depth_weighted` channel requires orderbook data: Binance orderbook is available via ccxt-pipeline (20 levels, Mar 2026+); Bybit orderbook is audited on 3TB-WDC (BTCUSDT historical, 2024-01-01 to 2025-08-20) and available to the current producer via ccxt-data-pipeline live Parquet from 2026-04-06 onward, with availability decided per requested window.
  - The existing `binance_standard_bias`, `funding_adjusted`, and `ensemble` models are parameter variations of `binance_standard` and MAY be added as additional channels post-MVP, but do not justify separate channels on their own.
- **FR-018**: The Binance producer MUST use DuckDB (read-only) as the data source for export. QuestDB hot data MUST NOT be used for artifact production because it is volatile and not reproducible for a given `snapshot_ts`.
- **FR-019**: The system MUST provide a reusable aggregation bridge that converts `List[LiquidationLevel]` into `(bucket_grid, long_distribution, short_distribution)`. This bridge MUST be independent of the API router and usable by all model channels.

### Non-Functional Requirements

- **NFR-001**: Internal monetary and liquidation calculations MUST continue to respect the project constitution for calculation precision. Exported JSON artifacts MAY serialize prices, bucket grids, and distributions at IEEE 754 float64 precision because this contract covers snapshot interchange, not live margin arithmetic.
- **NFR-002**: One exchange snapshot export SHOULD complete in under 10 seconds for an already-available input set.
- **NFR-003**: One week of backfill for a single exchange/symbol SHOULD complete in under 10 minutes, excluding external source download time.
- **NFR-004**: Status and provenance metadata SHOULD be parseable via plain JSON loading without importing Python code from this repo.

### Key Entities

- **ModeledSnapshotArtifact**: One modeled liquidation-map output for one exchange, symbol, model channel, and `snapshot_ts`.
- **ModeledSnapshotManifest**: One manifest describing availability, paths, and provenance for one requested exchange/symbol/timestamp export.
- **SourceReadinessReport**: One machine-readable report describing whether a source input class is present, persisted, and admissible for export.
- **BackfillBatchRecord**: One interval-level record describing coverage, gaps, failures, and deterministic input identity for a historical export run.
- **InputIdentityRecord**: One immutable provenance block tying an export to exact source files, timestamps, digests, or retained source manifests.

## Initial Contract Shape

Each `ModeledSnapshotArtifact` MUST contain at least:

- `exchange`
- `model_id`
- `symbol`
- `snapshot_ts`
- `reference_price`
- `bucket_grid`
- `long_distribution`
- `short_distribution`
- `source_metadata`
- `generation_metadata`

Suggested `generation_metadata` fields:

- `run_id`
- `run_reason`
- `run_ts`
- `producer_version`
- `producer_cadence`
- `input_window`

Suggested `source_metadata` fields:

- source input classes used
- canonical source root
- source timestamps or anchors
- logic family / builder name
- immutable input-identity references
- notes on blocked, partial, or degraded states

## Canonical Export Layout

Each exchange export root uses the same high-level layout:

- `data/validation/modeled_snapshots/{exchange}/artifacts/{symbol}/{snapshot_ts}/`
- `data/validation/modeled_snapshots/{exchange}/manifests/{symbol}/`
- `data/validation/modeled_snapshots/{exchange}/batches/`

Rules:

- artifact and manifest filenames MUST be derived from canonical `snapshot_ts`
- consumers MUST be able to start from a manifest path only
- batch records MUST summarize interval-level coverage and provenance without
  requiring artifact directory scans

## Success Criteria

- **SC-001**: Binance can be exported as a manifest-addressable modeled snapshot without requiring a consumer to call repo-internal Python code.
- **SC-002**: Bybit cannot accidentally masquerade as implemented; blocked state is explicit until source persistence is verified.
- **SC-003**: One consumer parser can load both Binance and Bybit manifests using the same top-level schema and availability semantics.
- **SC-004**: Deterministic backfill claims are auditable from manifest and batch metadata.
- **SC-005**: The resulting contract is reusable by NT or any other consumer regardless of whether integration later happens via files, REST, WebSocket, or Redis.

## Scope Boundary

### In Scope

- producer contract
- manifest layout
- provenance and input identity
- readiness gates
- deterministic backfill

### Not In Scope

- NT connector implementation
- WebSocket endpoint implementation
- Redis fan-out
- fixing the external downloader repo inside this repo
- exchange ranking or signal weighting

## Model Quality: LOB-Aware Channels

Each exchange exports two genuinely different model paradigms:

1. **`{exchange}_standard`** (aggregate statistical): estimates liquidation distributions
   from OI, trades, and funding. Simpler, works with less data, but does not account
   for actual book liquidity.

2. **`depth_weighted`** (LOB-aware): weights liquidation cluster probability by actual
   orderbook depth at each price level. Thin book = cascade more likely to reach that
   level. This produces higher-quality heatmaps because it reflects real market
   microstructure, not just aggregate statistics.

LOB data sources:
- **Binance**: ccxt-data-pipeline orderbook collector, 20 levels, 720k snapshots/day (Mar 2026+)
- **Bybit**: historical BTCUSDT orderbook on 3TB-WDC (2024-01-01 to 2025-08-20) plus ccxt-data-pipeline live Parquet from 2026-04-06 onward. Current producer availability is limited to ccxt-data-pipeline Parquet; historical-only 3TB-WDC windows remain `blocked_source_unverified` until a reader/normalizer is implemented, and uncovered gaps remain blocked or partial.

Future evolution (out of scope for this spec):
- **`cascade_sim`**: simulate how a liquidation event propagates through the orderbook,
  estimating second-order price impact and cascade depth. Requires processing-intensive
  simulation beyond formula-based approaches.

## Assumptions

- Binance source inputs already available in this repo are sufficient to build the first baseline modeled export
- The Hyperliquid producer/export work in `spec-029` is mature enough to reuse its contract patterns directly
- HL experts (v1-v5) are NOT transferable to CEX: they depend on per-user ABCI state unique to HL L1
- Bybit baseline model channels (OI + trades + funding + klines) have sufficient source data available now
- Bybit `depth_weighted` can be `available` for windows covered by ccxt-data-pipeline live Parquet. 3TB-WDC historical orderbook is audited but remains `blocked_source_unverified` until a producer-readable historical bridge exists, and uncovered historical gaps MUST NOT be marked available.
- Bybit will need exchange-specific MMR tiers (different from Binance) for a `BybitStandardModel`
- If the canonical storage root changes from the current 3TB WDC expectation, the readiness contract will be updated explicitly rather than implied silently
