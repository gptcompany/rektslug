# Tasks: Visual Comparison Harness

**Input**: `specs/020-visual-comparison-harness/spec.md`
**Dependencies**: `spec-016`, `spec-017`, future calibration specs
**Feature Type**: Shared validation infrastructure

## Phase 1: Inventory

- [ ] T001 Inventory current screenshot/validation scripts and manifest formats
- [ ] T002 Identify what is reusable vs what is liq-map-specific today
- [ ] T003 Define the minimal common manifest schema for screenshot-based comparison
- [ ] T004 Verify Playwright + Chromium are the canonical browser tooling for the harness

## Phase 2: Harness Surface

- [ ] T005 Define a provider-agnostic runner interface
- [ ] T006 Define product adapters (`liq-map` first, `liq-heat-map` later)
- [ ] T007 Define scoring outputs and threshold policy

## Phase 3: Liq-Map First Integration

- [ ] T008 Wire the harness to the existing local/CoinAnK liq-map validation path
- [ ] T009 Wire the harness to the Coinglass liq-map validation path
- [ ] T010 Emit one normalized screenshot-comparison report per run

## Phase 4: Extensibility

- [ ] T011 Add placeholders/interfaces for future heatmap adapters
- [ ] T012 Ensure manifests can represent both timeframe-style and window-style runs
- [ ] T013 Add tests for manifest/score compatibility across adapters

## Phase 5: Documentation

- [ ] T014 Document how calibration specs consume the harness
- [ ] T015 Document how future heatmap specs will plug into the harness
