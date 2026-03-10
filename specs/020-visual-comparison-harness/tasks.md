# Tasks: Visual Comparison Harness

**Input**: `specs/020-visual-comparison-harness/spec.md`
**Dependencies**: `spec-016`, `spec-017`, future calibration specs
**Feature Type**: Shared validation infrastructure

## Phase 1: Inventory

- [ ] T001 Inventory current screenshot/validation scripts and manifest formats
- [ ] T002 Identify what is reusable vs what is liq-map-specific today
- [ ] T003 Define the minimal common manifest schema for screenshot-based comparison
- [ ] T004 Verify Playwright + Chromium are the canonical browser tooling for the harness
- [ ] T005 Identify the current renderer assumptions baked into the existing Plotly-specific scripts

## Phase 2: Harness Surface

- [ ] T006 Define a provider-agnostic runner interface
- [ ] T007 Define product adapters (`liq-map` first, `liq-heat-map` later)
- [ ] T008 Define renderer adapters (`plotly` first, `lightweight` reserved)
- [ ] T009 Define scoring outputs and threshold policy

## Phase 3: Liq-Map First Integration

- [ ] T010 Wire the harness to the existing local/CoinAnK liq-map validation path on `plotly`
- [ ] T011 Wire the harness to the Coinglass liq-map validation path on `plotly`
- [ ] T012 Emit one normalized screenshot-comparison report per run

## Phase 4: Extensibility

- [ ] T013 Add placeholders/interfaces for future `liq-heat-map` product adapters
- [ ] T014 Add placeholders/interfaces for future `lightweight` renderer adapters
- [ ] T015 Ensure manifests can represent both timeframe-style and window-style runs
- [ ] T016 Add tests for manifest/score compatibility across product and renderer adapters

## Phase 5: Documentation

- [ ] T017 Document how calibration specs consume the harness
- [ ] T018 Document how future heatmap specs will plug into the harness
- [ ] T019 Document that Counterflow enters as a `lightweight` renderer adapter, not as a special-case global path
