# Tasks: Visual Comparison Harness

**Input**: `specs/020-visual-comparison-harness/spec.md`
**Dependencies**: `spec-016`, `spec-017`, future calibration specs
**Feature Type**: Shared validation infrastructure

## Execution Order Note

- Milestone 1 is the only active implementation target until it is green
- Milestone 1 Phase 1-2 can start immediately and run in parallel with `spec-018` / `spec-019`
- Milestone 1 Phase 3+ should begin only after at least the `spec-018` profile surface exists
- Milestone 2 starts only after the Milestone 1 MVP is green on the locked matrix
- Milestone 3 starts only after Milestone 2 hardening gates are green
- `spec-021` should consume the renderer-adapter seams from this spec, not bypass them
- The first concrete green path in this spec is `local + CoinAnK + liq-map + plotly`
- Live Coinglass visual wiring is deferred until canonical URLs and capture invariants are documented
- Task ids with an `a` suffix indicate review/checkpoint gates attached to the preceding numbered task

## Milestone 1: MVP

### Phase 1: Inventory

- [ ] T001 Inventory current screenshot/validation scripts and manifest formats
- [ ] T002 Identify what is reusable vs what is liq-map-specific today
- [ ] T003 Define the minimal common manifest and score JSON schemas for screenshot-based comparison
- [ ] T004 Verify Playwright + Chromium are the canonical browser tooling for the harness
- [ ] T005 Lock the first-cut matrix to `BTC/ETH x 1d/1w` on local/CoinAnK `liq-map`
- [ ] T006 Identify the current renderer assumptions baked into the existing Plotly-specific scripts

### Phase 2: Contracts and RED Tests

- [ ] T007a Write failing test: manifest JSON validates against the required field schema
- [ ] T007b Write failing test: adapter dispatch routes `product + renderer` to the correct handler
- [ ] T007c Write failing test: unsupported `product + renderer` combination fails before capture
- [ ] T007d Write failing test: local chart not ready -> `ready=false`, `tier1_pass=false`, `score=0`
- [ ] T007e Write failing test: provider unreachable -> non-zero exit and partial manifest with failure reason
- [ ] T007f Write failing test: score threshold gate returns non-zero when `score < pass_threshold`
- [ ] T007g Write failing test: re-running the same matrix entry with the same `run_id` produces identical artifact paths and `schema_version`
- [ ] T008 Define a provider-agnostic runner interface
- [ ] T009 Define product adapters (`liq-map` first, `liq-heat-map` later)
- [ ] T010 Define renderer adapters (`plotly` first, `lightweight` reserved)
- [ ] T011 Define first-cut scoring outputs and threshold policy: Tier-1 gate, `0/100` on Tier-1 failure, otherwise `tier2 + tier3`, pass threshold `95`
- [ ] T011a Review and sign off the first-cut scoring formula against the current `validate_liqmap_visual.py` checklist semantics before wiring the MVP path

### Phase 3: Liq-Map MVP Integration

- [ ] T012 Implement local page capture for `liq-map + plotly` against the locked `BTC/ETH x 1d/1w` matrix
- [ ] T013 Implement CoinAnK provider capture with `capture_mode` tracking and fallback handling
- [ ] T014 Implement the manifest writer: emit one normalized manifest JSON per comparison pair
- [ ] T015 Implement the scorer: emit one normalized score JSON per comparison pair with Tier-1 gate semantics
- [ ] T016 Validate NFR gates: runtime `< 120s`, manifest+score `< 1 MB`, timestamp presence, and non-zero exit on threshold/provider failure

## Milestone 2: Hardening

### Phase 4: Hardening Gates

- [ ] T017 Validate runtime `< 120s`, manifest+score `< 1 MB`, timestamp presence, and non-zero exit on threshold/provider failure under the live MVP path
- [ ] T018 Re-run the locked matrix and confirm deterministic naming/artifact paths under repeated `run_id` conventions
- [ ] T019 Verify partial-manifest behavior on provider-unreachable and local-not-ready failure modes using the MVP path
- [ ] T020 Freeze the Milestone 1 manifest/score schema and scoring semantics as the stable contract consumed by later specs

## Milestone 3: Extension

### Phase 5: Extensibility
- [ ] T021 Define the `liq-heat-map` adapter seam without wiring a live provider path yet
- [ ] T022 Define the `lightweight` renderer seam without making it the default renderer
- [ ] T023 Ensure manifests can represent both timeframe-style and window-style runs and reject incompatible pairings
- [ ] T024 Document Coinglass visual adapter prerequisites instead of wiring a speculative live path
- [ ] T025 Extend tests for manifest/score compatibility across product and renderer adapters

### Phase 6: Documentation

- [ ] T026 Document how calibration specs consume the harness
- [ ] T027 Document how future heatmap specs will plug into the harness
- [ ] T028 Document that Counterflow enters as a `lightweight` renderer adapter, not as a special-case global path
