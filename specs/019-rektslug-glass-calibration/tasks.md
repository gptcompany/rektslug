# Tasks: Rektslug-Glass Calibration

**Input**: `specs/019-rektslug-glass-calibration/spec.md`
**Dependencies**: `spec-017` comparison artifacts/workflow and the reusable profile-surface mechanism introduced by `spec-018`
**Feature Type**: Model calibration profile

## Phase 1: Baseline Audit

- [X] T001 Collect the current `spec-017` Coinglass comparison metrics for `BTC/ETH x 1d/1w`
- [X] T002 Define acceptance thresholds for `rektslug-glass`
- [X] T003 [P] Identify adjustable local parameters that influence Coinglass parity

## Phase 2: Profile Surface

- [X] T004 Reuse the explicit profile/config surface introduced by `spec-018` to add `rektslug-glass`
- [X] T005 Record the active local profile in manifests/reports
- [X] T006 Add tests covering profile selection and isolation from `rektslug-default` and `rektslug-ank`

## Phase 3: Calibration Loop

- [X] T007 Run BTC 1D calibration against Coinglass
- [X] T008 Run BTC 1W calibration against Coinglass
- [X] T009 Run ETH 1D calibration against Coinglass
- [X] T010 Run ETH 1W calibration against Coinglass
- [X] T011 Keep only candidates that improve the agreed metric set

## Phase 4: Validation

- [X] T012 Freeze the chosen `rektslug-glass` profile
- [X] T013 Re-run the full matrix against Coinglass
- [X] T014 Confirm the calibrated profile beats the default local profile on the majority of target metrics
- [X] T015 Confirm CoinAnK-oriented and default profiles are unaffected

## Phase 5: Documentation

- [X] T016 Document Coinglass-focused calibration commands
- [X] T017 Record final acceptance metrics and profile identity

## Completion Notes

- Accepted calibration artifact: `data/validation/provider_comparisons/20260311T005526Z_calibration_rektslug-glass.json`
- Acceptance result: `accepted`, `3/4` matrix entries passing, `0` critical regressions
- Runtime gate: `7.6s` total wall-clock
- Coinglass-specific threshold note: `bucket_overlap` acceptance uses `>= 5%` aligned-grid improvement because `liqMap` clusters under top-level price buckets
