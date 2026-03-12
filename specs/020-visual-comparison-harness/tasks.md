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

- [x] T001 Inventory current screenshot/validation scripts and manifest formats
- [x] T002 Identify what is reusable vs what is liq-map-specific today
- [x] T003 Define the minimal common manifest and score JSON schemas for screenshot-based comparison
- [x] T004 Verify Playwright + Chromium are the canonical browser tooling for the harness
- [x] T005 Lock the first-cut matrix to `BTC/ETH x 1d/1w` on local/CoinAnK `liq-map`
- [x] T006 Identify the current renderer assumptions baked into the existing Plotly-specific scripts

### Phase 2: Contracts and RED Tests

- [x] T007a Write failing test: manifest JSON validates against the required field schema
- [x] T007b Write failing test: adapter dispatch routes `product + renderer` to the correct handler
- [x] T007c Write failing test: unsupported `product + renderer` combination fails before capture
- [x] T007d Write failing test: local chart not ready -> `ready=false`, `tier1_pass=false`, `score=0`
- [x] T007e Write failing test: provider unreachable -> non-zero exit and partial manifest with failure reason
- [x] T007f Write failing test: score threshold gate returns non-zero when `score < pass_threshold`
- [x] T007g Write failing test: re-running the same matrix entry with the same `run_id` produces identical artifact paths and `schema_version`
- [x] T008 Define a provider-agnostic runner interface
- [x] T009 Define product adapters (`liq-map` first, `liq-heat-map` later)
- [x] T010 Define renderer adapters (`plotly` first, `lightweight` reserved)
- [x] T011 Define first-cut scoring outputs and threshold policy: Tier-1 gate, `0/100` on Tier-1 failure, otherwise `tier2 + tier3`, pass threshold `95`
- [x] T011a Review and sign off the first-cut scoring formula against the current `validate_liqmap_visual.py` checklist semantics before wiring the MVP path

### Phase 3: Liq-Map MVP Integration

- [x] T012 Implement local page capture for `liq-map + plotly` against the locked `BTC/ETH x 1d/1w` matrix
- [x] T013 Implement CoinAnK provider capture with `capture_mode` tracking and fallback handling
- [x] T014 Implement the manifest writer: emit one normalized manifest JSON per comparison pair
- [x] T015 Implement the scorer: emit one normalized score JSON per comparison pair with Tier-1 gate semantics
- [x] T016 Validate NFR gates: runtime `< 120s`, manifest+score `< 1 MB`, timestamp presence, and non-zero exit on threshold/provider failure

## Milestone 2: Hardening

### Phase 4: Hardening Gates

- [x] T017 Validate runtime `< 120s`, manifest+score `< 1 MB`, timestamp presence, and non-zero exit on threshold/provider failure under the live MVP path
- [x] T018 Re-run the locked matrix and confirm deterministic naming/artifact paths under repeated `run_id` conventions
- [x] T019 Verify partial-manifest behavior on provider-unreachable and local-not-ready failure modes using the MVP path
- [x] T020 Freeze the Milestone 1 manifest/score schema and scoring semantics as the stable contract consumed by later specs

## Milestone 3: Extension

### Phase 5: Extensibility
- [x] T021 Define the `liq-heat-map` adapter seam without wiring a live provider path yet
- [x] T022 Define the `lightweight` renderer seam without making it the default renderer
- [x] T023 Ensure manifests can represent both timeframe-style and window-style runs and reject incompatible pairings
- [x] T024 Document Coinglass visual adapter prerequisites instead of wiring a speculative live path
- [x] T025 Extend tests for manifest/score compatibility across product and renderer adapters

### Phase 6: Documentation

- [ ] T026 Document how calibration specs consume the harness
- [ ] T027 Document how future heatmap specs will plug into the harness
- [ ] T028 Document that Counterflow enters as a `lightweight` renderer adapter, not as a special-case global path

## Completion Notes

- Milestone 1 MVP is green for the locked `BTC/ETH x 1d/1w` matrix on the `local + CoinAnK + liq-map + plotly` path.
- The live matrix smoke was executed against a worktree-served `uvicorn` instance on `http://127.0.0.1:8012` using `scripts/run_visual_harness.py`.
- Successful live run ids: `spec020-btc1d`, `spec020-btc1w`, `spec020-eth1d`, `spec020-eth1w`.
- All four live matrix entries produced `status=pass`, `score=100`, `capture_mode=screenshot_crop`, and artifact sizes well below the `< 1 MB` budget.
- Local failure handling is now explicit and fast-failing, with `local.page_state.failure_reason` populated for backend/page load failures.
- Provider failure handling now preserves partial `CoinAnK` capture context in partial manifests instead of collapsing to a generic error only.
- Milestone 1 contract is frozen at `schema_version = "1.0"` for later specs, with score JSON required for completed pairs and partial-manifest-only behavior retained for provider pre-score failures.
- The frozen MVP contract now explicitly includes `elapsed_seconds`, `artifact_bytes`, `nfr_failures`, optional `local.page_state`, optional `provider.capture_info`, and `failure_reason` semantics.
- Milestone 3 extension seams are now defined in code: `liq-map` remains timeframe-only on `plotly`, while `liq-heat-map` supports both timeframe/window entry modes and reserves both `plotly` and `lightweight` renderer adapters without wiring a live provider path yet.
- Compatibility tests now cover `window`-style manifests, deterministic artifact naming for `window` runs, and successful adapter resolution for `liq-heat-map` plus `lightweight`.
