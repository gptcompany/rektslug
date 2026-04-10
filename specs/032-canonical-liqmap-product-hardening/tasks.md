# Tasks: spec-032 Canonical Liq-Map Product Hardening

## Phase 1: Scope Freeze

- [ ] T001 Freeze the canonical liq-map browser/API matrix for Binance, Bybit, and Hyperliquid
- [ ] T002 Freeze `surface` as a first-class workflow axis with enum `{public, legacy}`
- [ ] T003 Explicitly mark provider-parity math and heatmap work out of scope for this spec

## Phase 2: Workflow Surface Contract

- [x] T004R RED: Write failing tests for `scripts/validate_liqmap_visual.py` surface selection and defaults
- [x] T005 Add `surface` handling to `scripts/validate_liqmap_visual.py`
- [x] T006R RED: Write failing tests for visual-harness local liq-map capture using explicit `surface`
- [x] T007 Add `surface` handling to the liq-map visual harness local provider flow
- [x] T008R RED: Write failing tests for `scripts/capture_provider_api.py` / `scripts/run_provider_api_comparison.py` surface selection
- [x] T009 Add explicit `surface` selection to capture/comparison entrypoints
- [x] T010 Make product-facing liq-map workflows default to `surface=public`
- [x] T011 Make calibration/model-inspection workflows declare `surface=legacy` explicitly

## Phase 3: Manifest and Report Semantics

- [x] T012R RED: Write failing tests for manifest/report persistence of requested/effective surface
- [x] T013 Persist `requested_surface`, `effective_surface`, and effective endpoint path in liq-map workflow artifacts
- [x] T014 Propagate surface metadata through comparison/gap-analysis/calibration report layers
- [x] T015 Remove workflow assumptions that infer surface only from ad hoc endpoint substrings

## Phase 4: Binance Public Fallback Provenance

- [ ] T016R RED: Write failing test that distinguishes Binance public artifact-backed serving from Binance public legacy fallback
- [ ] T017 Freeze the Binance public fallback policy under this spec
- [ ] T018 Expose public-serving provenance for Binance in a machine-readable way suitable for validators/manifests
- [x] T019 Ensure Hyperliquid public runs cannot silently degrade to legacy `/liquidations/levels`

## Phase 5: Validation and Documentation

- [ ] T020 Keep canonical-route browser coverage for Binance, Bybit, and Hyperliquid public flows
- [x] T021 Keep regression coverage for legacy calibration flows after explicit `surface` adoption
- [ ] T022 Update active liq-map docs/runbooks to reflect the canonical/public-vs-legacy split
- [ ] T023 Produce final handoff documenting the frozen product boundary and the remaining follow-up spec for provider-parity models
