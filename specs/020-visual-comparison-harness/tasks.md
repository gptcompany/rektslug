# Tasks: Visual Comparison Harness

**Input**: `specs/020-visual-comparison-harness/spec.md`
**Dependencies**: `spec-016`, `spec-017`, future calibration specs
**Feature Type**: Shared validation infrastructure

## Execution Order Note

- Phase 1-2 can start immediately and run in parallel with `spec-018` / `spec-019`
- Phase 3+ should begin only after at least the `spec-018` profile surface exists
- `spec-021` should consume the renderer-adapter seams from this spec, not bypass them
- The first concrete green path in this spec is `local + CoinAnK + liq-map + plotly`
- Live Coinglass visual wiring is deferred until canonical URLs and capture invariants are documented

## Phase 1: Inventory

- [ ] T001 Inventory current screenshot/validation scripts and manifest formats
- [ ] T002 Identify what is reusable vs what is liq-map-specific today
- [ ] T003 Define the minimal common manifest and score JSON schemas for screenshot-based comparison
- [ ] T004 Verify Playwright + Chromium are the canonical browser tooling for the harness
- [ ] T005 Lock the first-cut matrix to `BTC/ETH x 1d/1w` on local/CoinAnK `liq-map`
- [ ] T006 Identify the current renderer assumptions baked into the existing Plotly-specific scripts

## Phase 2: Contracts and RED Tests

- [ ] T007 Write failing tests for manifest schema, adapter dispatch, unsupported combinations, local-not-ready behavior, provider-unreachable partial-manifest behavior, and score-threshold behavior
- [ ] T008 Define a provider-agnostic runner interface
- [ ] T009 Define product adapters (`liq-map` first, `liq-heat-map` later)
- [ ] T010 Define renderer adapters (`plotly` first, `lightweight` reserved)
- [ ] T011 Define first-cut scoring outputs and threshold policy: Tier-1 gate, `0/100` on Tier-1 failure, otherwise `tier2 + tier3`, pass threshold `95`

## Phase 3: Liq-Map MVP Integration

- [ ] T012 Implement the local/CoinAnK `liq-map + plotly` harness path against the locked `BTC/ETH x 1d/1w` matrix
- [ ] T013 Emit one normalized manifest JSON and one normalized score JSON per run, including capture timestamps, provider capture mode, and partial-manifest failure details when capture aborts
- [ ] T014 Validate runtime `< 120s`, manifest+score size `< 1 MB`, timestamp presence, and non-zero exit on threshold/provider failure for the MVP path

## Phase 4: Extensibility

- [ ] T015 Define the `liq-heat-map` adapter seam without wiring a live provider path yet
- [ ] T016 Define the `lightweight` renderer seam without making it the default renderer
- [ ] T017 Ensure manifests can represent both timeframe-style and window-style runs and reject incompatible pairings
- [ ] T018 Document Coinglass visual adapter prerequisites instead of wiring a speculative live path
- [ ] T019 Extend tests for manifest/score compatibility across product and renderer adapters

## Phase 5: Documentation

- [ ] T020 Document how calibration specs consume the harness
- [ ] T021 Document how future heatmap specs will plug into the harness
- [ ] T022 Document that Counterflow enters as a `lightweight` renderer adapter, not as a special-case global path
