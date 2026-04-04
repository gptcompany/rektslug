# Implementation Plan: Hyperliquid Expert Snapshot Producer Contract

**Spec**: `specs/029-hl-expert-snapshot-producer-contract/spec.md`
**Feature Type**: Contract hardening + producer export implementation
**Branch**: master

## Summary

`spec-029` turns the current Hyperliquid sidecar outputs in `rektslug` into a
stable producer contract for the external evaluator defined in
`/media/sam/1TB/nautilus_dev/specs/061-liquidation-map-expert-evaluator/spec.md`.
The goal is not to move replay, scoring, or weighting into `rektslug`. The
goal is to make `rektslug` a reliable producer of expert snapshot artifacts,
manifests, run metadata, and historical backfill batches that can be consumed
without importing internal script logic.

## Technical Context

### Current State

- `scripts/precompute_hl_sidecar.py` already materializes Hyperliquid sidecar
  artifacts into `data/cache/` and is designed for periodic cron execution.
- `scripts/compare_hl_sidecar_variants.py` already normalizes variant payloads
  into comparable distributions and reconstructs `v2` from local CoinGlass
  replay when needed.
- The runbook
  `docs/runbooks/hyperliquid-liqmap-checkpoint.md` already records the current
  product decisions:
  - `v1` stays canonical
  - `v2` stays `shadow/control`
  - `v5` stays experimental
- `spec-061` in `nautilus_dev` now expects a stable producer contract rather
  than ad hoc cache-path knowledge.

### Existing Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| `scripts/precompute_hl_sidecar.py` | Exists | Current periodic producer path; writes atomic JSON sidecar outputs |
| `scripts/compare_hl_sidecar_variants.py` | Exists | Variant normalization/report path; already reconstructs `v2` from local replay |
| `data/cache/hl_sidecar_*.json` | Exists | Current cache outputs for producer-side variants |
| `data/validation/comparison_hl_btc_variants_raw_usd.json` | Exists | Current payload-level comparison artifact |
| `docs/runbooks/hyperliquid-liqmap-checkpoint.md` | Exists | Canonical decision log for current Hyperliquid branch status |
| `specs/026-liqmap-model-calibration/*` | Exists | Sidecar and validation groundwork feeding the current producer logic |

### Source Documents

- `specs/029-hl-expert-snapshot-producer-contract/spec.md`
- `specs/026-liqmap-model-calibration/spec.md`
- `docs/runbooks/hyperliquid-liqmap-checkpoint.md`
- `scripts/precompute_hl_sidecar.py`
- `scripts/compare_hl_sidecar_variants.py`
- `/media/sam/1TB/nautilus_dev/specs/061-liquidation-map-expert-evaluator/spec.md`

## Architecture

```text
current Hyperliquid sidecar builders / caches / replay-derived control inputs
        ->
producer-side normalization into expert snapshot artifacts
        ->
manifest + run metadata + backfill batch records
        ->
stable export surface under `data/validation/expert_snapshots/hyperliquid/`
        ->
consumer pickup by `nautilus_dev` evaluator
```

## Architecture Boundary

- `rektslug` owns expert generation, normalization, manifesting, and backfill.
- `rektslug` does not own replay evaluation, labels, metrics, or weighting.
- `nautilus_dev` consumes exported expert artifacts and aligns them to replay.
- No part of this plan should introduce a hidden dependency on `rektslug`
  script internals from the consumer side.

## What Already Works

- current builder paths can produce `v1`, `v4`, and `v5` style cache artifacts
- current raw-USD variant comparison can normalize and compare sidecar payloads
- current `v2` reconstruction path already resolves a CoinGlass replay/control
  payload from local retained data
- current runbook decisions already define the policy status of `v1`, `v2`,
  and `v5`

## What Needs Work

1. freeze a machine-readable snapshot schema for `v1`..`v5`
2. create manifest-driven export layout instead of path-guessing
3. define canonical timestamp semantics (`snapshot_ts` vs `run_ts`) and stable
   timestamp-derived naming
4. record deterministic producer run metadata (`run_id`, `run_reason`,
   `run_ts`, `last_actual_run_ts`)
5. make missing-expert and source/decode failures explicit, while still
   preserving all five expert channels at manifest level
6. define a formal common-grid export rule so the consumer does not rebucket
   ad hoc
7. add immutable input identity metadata for auditable deterministic backfill
8. support historical backfill as a declared batch output rather than a loose
   script convention
9. document and test the producer/consumer boundary against `spec-061`,
   including the current `15m` producer cadence versus future `5m`
   evaluator-side sampling

## Deliverables

### D1. Snapshot Schema

Create a strict producer schema for one expert artifact containing at least:

- `expert_id`
- `symbol`
- `snapshot_ts`
- `reference_price`
- `bucket_grid`
- `long_distribution`
- `short_distribution`
- `research_policy_tag`
- `source_metadata`
- `generation_metadata`

### D2. Manifest Contract

Create a manifest/index contract that:

- resolves all five expert channels for one timestamp or batch
- reports missing experts explicitly
- records source/decode failures explicitly
- does not require downstream path heuristics

### D2A. Canonical Time Identity

Create a canonical time contract that distinguishes:

- `snapshot_ts` as exported evaluation-point identity
- `run_ts` as actual producer execution time

and uses stable timestamp-derived naming in manifests and artifact paths.

### D3. Producer Run Record

Create metadata that allows the consumer to reconstruct:

- why a run happened
- when it happened
- whether it is `baseline`, `extra`, `manual`, or `backfill`
- which prior actual run it follows
- whether it re-anchors baseline scheduling

### D3A. Input Identity Record

Create immutable source identity metadata that allows deterministic reruns to
be audited, such as:

- source manifest ids
- capture ids
- content digests
- retained snapshot ids

### D4. Export Layout

Create a stable export location under:

- `data/validation/expert_snapshots/hyperliquid/`

with manifests, artifacts, and backfill batch records.

### D5. Historical Backfill

Support bounded-interval historical export with:

- explicit timeline policy
- symbol/expert coverage
- gap reporting
- deterministic rerun behavior

### D6. Common Grid Contract

Define and enforce a machine-readable common-grid export contract so all expert
artifacts for one `snapshot_ts` are already normalized before consumer pickup.

## Phases

1. Contract lock-in (policy tags, field sets, timestamp semantics).
2. Schema and export primitives (TDD: RED tests first, then implementation).
3. Manifest-first export layout (TDD: RED tests first, then implementation).
4. Producer run metadata and scheduling semantics (TDD: RED tests first).
5. Current builder integration (TDD: RED tests first).
6. Historical backfill batch contract (TDD: RED tests first).
7. Integration validation and consumer handoff.

Each implementation phase (2-6) begins with RED failing tests before any
production code is written, in compliance with Constitution MUST #2 (TDD).

## Non-Functional Requirements

- NFR-001: Numeric precision — float64 minimum for prices, grids, and
  distributions. Decimal128 not required (snapshot export, not live margin).
- NFR-002: Export performance — single batch < 10s, one-week backfill < 10 min.
- NFR-003: Storage footprint — < 500 KB per snapshot batch (JSON).

## Acceptance Notes

- `v1` remains canonical in producer metadata.
- `v2` remains `shadow/control` in producer metadata.
- every manifest always contains all five expert channels, even when one or
  more are unavailable.
- `v3`, `v4`, and `v5` remain experimental branches unless later promoted by a
  separate decision.
- `snapshot_ts` is the canonical exported time identity; `run_ts` remains
  execution provenance.
- The producer contract must stay stable even if cache file names or internal
  builder wiring change. Existing `data/cache/hl_sidecar_*.json` files coexist
  unchanged alongside the new export layout during MVP.
- The first consumer is `spec-061`; the contract must optimize for consumer
  clarity, not producer convenience.
- current producer cadence remains `15m` (the cadence actually supported by
  `rektslug`); denser evaluator-side sampling remains a consumer concern until
  a separate producer-side change lands.
- TDD discipline: every implementation phase begins with RED failing tests
  before production code.

## Risks

- leaving path-derived assumptions in place and forcing the consumer to guess
- treating missing artifacts as implicit gaps instead of explicit manifest
  entries
- under-specifying `v2` provenance and shadow semantics
- leaving timestamp semantics ambiguous between identity time and run time
- claiming determinism without immutable source identity
- leaving common-grid normalization ambiguous and pushing rebucketing back to
  the consumer
- allowing run timing metadata to remain too weak for replay alignment
- building a backfill export that is “best effort” but not auditable
- leaking evaluator concerns back into `rektslug`

## Success Criteria

- a consumer can resolve all available experts for one timestamp from a
  manifest only, with all five channels present
- `v2` is always explicitly marked `shadow/control`
- `snapshot_ts` and `run_ts` are unambiguous and stable across artifacts,
  manifests, and batch records
- exported artifacts declare a common normalized grid with no consumer-side
  inference required
- producer run metadata is strong enough for replay alignment decisions
- deterministic backfill claims are backed by immutable input identity
- backfill batches expose coverage and gaps machine-readably
- `nautilus_dev` can consume exports without importing `rektslug` internals
