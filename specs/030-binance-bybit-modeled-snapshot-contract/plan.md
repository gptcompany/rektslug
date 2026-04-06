# Implementation Plan: Binance/Bybit Modeled Snapshot Contract

**Spec**: `specs/030-binance-bybit-modeled-snapshot-contract/spec.md`
**Feature Type**: Producer contract + source readiness gate + deterministic export
**Branch**: master

## Summary

`spec-030` extends the contract discipline introduced in `spec-028` and
`spec-029` to Binance and Bybit.

The immediate deliverable is not a new live API. The immediate deliverable is a
stable modeled-snapshot producer contract that:

- reuses the already-working Binance model/runtime
- exposes manifest-addressable artifacts for consumers
- records immutable provenance and input identity
- prevents Bybit from being declared ready until its source persistence is
  verified

## Technical Context

### Current State

- Binance already has working model/runtime pieces:
  - `src/liquidationheatmap/models/binance_standard.py`
  - `src/liquidationheatmap/api/routers/liquidations.py`
  - `src/liquidationheatmap/api/routers/market.py`
  - `scripts/precompute_heatmap_timeseries.py`
- Hyperliquid already has the closest existing producer/export implementation:
  - `src/liquidationheatmap/hyperliquid/snapshot_schema.py`
  - `src/liquidationheatmap/hyperliquid/export_layout.py`
  - `src/liquidationheatmap/hyperliquid/producer.py`
  - `src/liquidationheatmap/hyperliquid/backfill.py`
- Bybit is not operational as an exchange producer in rektslug:
  - `src/exchanges/bybit.py` is a stub (raises NotImplementedError)
  - `src/exchanges/aggregator.py` skips it when unimplemented
- However, Bybit data availability is better than originally assumed:
  - ccxt-data-pipeline daemon (live, default exchanges include bybit):
    - OHLCV: collecting since 2026-01-28
    - Open Interest: collecting since 2026-02-24
    - Funding Rate: collecting since 2026-02-24
    - Liquidations: streamed via WS but NOT persisted to Parquet catalog
  - bybit_data_downloader on 3TB-WDC (external repo):
    - Trades: 133GB, 2020-05-01 to 2026-04-04 (current)
    - Orderbook: 319GB, 2024-01-01 to 2025-09-24 (STALE — downloader stopped)
    - Funding rates: 328 files
    - Open Interest: 332 files
- Readiness is per-channel:
  - `bybit_standard` (OI + trades + funding + klines): data exists, readiness gate can pass
  - `depth_weighted` (requires orderbook): orderbook gap (Sep 2025 to present) being fixed in bybit_data_downloader and ccxt-data-pipeline; historical 319GB available for backtest

### Source Documents

- `specs/028-consumer-checkpoint-7d/spec.md`
- `specs/029-hl-expert-snapshot-producer-contract/spec.md`
- `specs/012-exchange-aggregation/spec.md`
- `specs/024-heatmap-timeseries-precomputation/spec.md`
- `src/liquidationheatmap/models/binance_standard.py`
- `src/liquidationheatmap/api/routers/liquidations.py`
- `src/exchanges/binance.py`
- `src/exchanges/bybit.py`

## Architecture

```text
existing exchange-specific source inputs
        ->
source audit + input identity capture
        ->
modeled snapshot normalization
        ->
manifest + artifact + batch record export
        ->
consumer pickup by file/artifact contract
```

## Architecture Boundary

- This plan produces artifacts and manifests.
- This plan does not choose whether downstream transport is REST, WebSocket, or
  Redis.
- Live-serving work remains separate:
  - WebSocket: `spec-025`
  - signals/Redis: existing signals path or future work

## What Already Works

- Binance modeling and REST serving already exist.
- Hyperliquid export primitives already exist and can be adapted.
- Current ingestion stack already provides a meaningful source base for Binance.

## What Needs Work

1. freeze a modeled-snapshot schema not tied to Hyperliquid expert semantics
2. define a clean export root for Binance and Bybit
3. extract the aggregation bridge from `liquidations.py:_aggregate_legacy_levels` into
   a reusable module that converts `List[LiquidationLevel]` into `(bucket_grid,
   long_distribution, short_distribution)` — this is required before any producer can
   write artifacts
4. define immutable input-identity rules for Binance exports
5. create manifest and backfill records for Binance
6. implement two genuinely different model channels per exchange:
   - `{exchange}_standard` (canonical): aggregate statistical — exchange-specific MMR tiers
   - `depth_weighted` (LOB-aware): orderbook depth weighting — shared paradigm, per-exchange data
   - The existing `binance_standard_bias`, `funding_adjusted`, `ensemble` are
     parameter variations of the same formula and do not justify separate channels
7. define an explicit readiness gate for Bybit (per-channel: `bybit_standard` vs `depth_weighted`)
8. produce a machine-readable Bybit source-readiness report
9. only after readiness passes per channel, implement Bybit export support

## Architectural Decisions

### Binance producer data source

The Binance producer MUST use DuckDB (read-only) as the source for deterministic
exports. QuestDB is excluded because its hot data window (≤14d) is volatile and
not reproducible for a given `snapshot_ts`.

**Implementation constraint**: The current `DuckDBService.calculate_liquidations_oi_based()`
is NOT snapshot_ts-addressable — it queries the latest OI and anchors the window from
`MAX(open_time)`. The producer MUST wrap or extend this query to accept an explicit
`snapshot_ts` parameter that pins the time window, so that identical `snapshot_ts` inputs
produce identical outputs (FR-014). This may require a thin query adapter that adds
`WHERE open_time <= :snapshot_ts` filtering before calling the existing calculation logic.

### Aggregation bridge

The transformation from `List[LiquidationLevel]` (individual liquidation points) to
`ModeledSnapshotArtifact` (bucketed distributions) requires an explicit aggregation
step. This logic currently lives embedded in `api/routers/liquidations.py` as
`_aggregate_legacy_levels()`. It must be extracted into a shared module at
`src/liquidationheatmap/contracts/aggregation.py` so that all model channels and
the producer can reuse it without importing the API router.

### Multi-channel Binance

All 4 existing Binance models implement the same `AbstractLiquidationModel` interface.
Adding a channel to the export requires only:
1. instantiate the model
2. call `calculate_liquidations()` with DuckDB-sourced inputs
3. pass through the shared aggregation bridge
4. write the artifact with its `model_id`

The producer iterates over a registry of enabled channels, similar to how the HL
producer iterates over expert IDs v1-v5.

### Why HL experts are NOT transferable

HL experts (v1-v5) depend on ABCI state snapshots: per-user positions, balances,
and cross-margin accounting from the Hyperliquid L1 validator node. This data does
not exist for centralized exchanges. Binance and Bybit only expose aggregate market
data (OI, trades, funding). The two paradigms are fundamentally different:

- HL: per-user position reconstruction → per-account liquidation solving
- CEX: aggregate OI + trades + funding → statistical liquidation estimation

This means Binance/Bybit models are inherently less precise at individual position
level, but serve their purpose for heatmap visualization and cluster detection.

### LOB-aware model channels (in scope — `depth_weighted`)

The `{exchange}_standard` models are purely formula-based on aggregate data.
The `depth_weighted` channel uses orderbook (LOB) data to weight liquidation
cluster probability by actual book liquidity at each price level. This is a
genuinely different paradigm that produces higher-quality heatmaps.

Both Binance and Bybit implement `depth_weighted`:

- **Binance**: orderbook available via ccxt-data-pipeline (20 levels, 720k
  snapshots/day, Mar 2026+). Ready now.
- **Bybit**: 319GB historical orderbook on 3TB-WDC (2024-01 to 2025-09).
  Collection gap (Sep 2025 to present) being fixed in bybit_data_downloader
  and ccxt-data-pipeline. The readiness gate for `depth_weighted` checks
  orderbook availability separately from `bybit_standard`.

Future evolution (out of scope): `cascade_sim` — simulate liquidation cascades
through the orderbook to estimate second-order price impact. Requires
processing-intensive simulation beyond formula-based approaches.

## Deliverables

### D1. Shared Modeled Snapshot Schema

One generic schema for:

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

### D2. Export Layout

Create a stable export location under:

- `data/validation/modeled_snapshots/binance/`
- `data/validation/modeled_snapshots/bybit/`

with timestamp-addressable artifacts, manifests, and batch records.

### D3. Binance Producer Path

Wrap the existing Binance model/runtime into a deterministic export path.

### D4. Bybit Source Readiness Gate

Define the conditions that must be true before Bybit can be exported as
`available`.

### D5. Backfill Contract

Support deterministic bounded backfill with explicit coverage and provenance.

## Phases

1. Contract lock-in
2. Binance source inventory and provenance design
3. Binance export implementation
4. Bybit readiness-gate definition
5. Bybit export implementation, gated on source readiness
6. Consumer handoff and documentation

Each implementation phase that changes code begins with RED tests before
production code.

## Acceptance Notes

- Binance is the first in-scope exchange because it already exists here.
- Bybit is intentionally split into:
  - source-readiness work
  - export work
- If Bybit source readiness is still unresolved, the correct output is an
  explicit blocked status, not a fake success.
- This spec should not distort `spec-029` expert semantics onto Binance/Bybit.
  Reuse the contract pattern, not the Hyperliquid naming.
- This spec should not collapse into transport work. Artifact contract first.

## Risks

- over-claiming Bybit readiness without auditable inputs
- coupling consumers to internal REST or Python code instead of manifests
- re-implementing Binance logic instead of wrapping the existing path
- mixing source-readiness concerns with live-transport concerns
- creating a contract that cannot prove deterministic reruns

## Success Criteria

- Binance export works as a manifest-addressable artifact producer
- Bybit blocked status is explicit and machine-readable until readiness passes
- one contract parser can read both Binance and Bybit exports
- the contract remains valid regardless of later delivery method
