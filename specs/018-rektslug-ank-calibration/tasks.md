# Tasks: Rektslug-Ank Calibration

**Input**: `specs/018-rektslug-ank-calibration/spec.md`
**Dependencies**: `spec-017` comparison artifacts and workflow
**Feature Type**: Model calibration profile

## Phase 1: Baseline Audit

- [ ] T001 Collect the current `spec-017` CoinAnk comparison metrics for `BTC/ETH x 1d/1w`
- [ ] T002 Define the exact metric set and acceptance thresholds for `rektslug-ank`
- [ ] T003 [P] Identify which local parameters are allowed to vary (bin size, weighting, scaling, grouping, range)

## Phase 2: Profile Surface

> **TDD order**: T004 writes failing tests first, T005-T006 implement to make them pass.

- [ ] T004 Write failing tests that assert profile selection (`rektslug-default` vs `rektslug-ank`) and manifest profile recording
- [ ] T005 Introduce an explicit `rektslug-ank` profile/config surface in the local workflow (GREEN for T004 tests)
- [ ] T006 Ensure manifests/reports record the active local profile name (GREEN for T004 manifest tests)

## Phase 3: Calibration Loop

- [ ] T007 Run calibration experiments on BTC 1D
- [ ] T008 Run calibration experiments on BTC 1W
- [ ] T009 Run calibration experiments on ETH 1D
- [ ] T010 Run calibration experiments on ETH 1W
- [ ] T011 Compare each candidate against the original local baseline and retain only improving changes
- [ ] T011b If no candidate meets the acceptance rule (3/5 metrics on 3/4 entries), preserve the default profile and document the failure in a JSON report

## Phase 4: Validation

- [ ] T012 Freeze the chosen `rektslug-ank` profile parameters in versioned config/code
- [ ] T013 Re-run the full `BTC/ETH x 1d/1w` matrix against CoinAnk and verify the wall-clock runtime stays below `NFR-001` (< 10 minutes)
- [ ] T014 Confirm the calibrated profile improves at least `3/5` core metrics on at least `3/4` matrix entries, with no critical regression (> 30% degradation) on any entry
- [ ] T015 Confirm the default local profile still works unchanged when selected explicitly

## Phase 5: Documentation

- [ ] T016 Document how to run CoinAnk-focused calibration and comparison
- [ ] T017 Record the final acceptance metrics and profile identity in artifacts/spec notes
