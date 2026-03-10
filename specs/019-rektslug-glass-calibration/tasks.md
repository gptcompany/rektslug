# Tasks: Rektslug-Glass Calibration

**Input**: `specs/019-rektslug-glass-calibration/spec.md`
**Dependencies**: `spec-017` comparison artifacts and workflow
**Feature Type**: Model calibration profile

## Phase 1: Baseline Audit

- [ ] T001 Collect the current `spec-017` Coinglass comparison metrics for `BTC/ETH x 1d/1w`
- [ ] T002 Define acceptance thresholds for `rektslug-glass`
- [ ] T003 [P] Identify adjustable local parameters that influence Coinglass parity

## Phase 2: Profile Surface

- [ ] T004 Introduce an explicit `rektslug-glass` profile/config surface
- [ ] T005 Record the active local profile in manifests/reports
- [ ] T006 Add tests covering profile selection and isolation from `rektslug-default` and `rektslug-ank`

## Phase 3: Calibration Loop

- [ ] T007 Run BTC 1D calibration against Coinglass
- [ ] T008 Run BTC 1W calibration against Coinglass
- [ ] T009 Run ETH 1D calibration against Coinglass
- [ ] T010 Run ETH 1W calibration against Coinglass
- [ ] T011 Keep only candidates that improve the agreed metric set

## Phase 4: Validation

- [ ] T012 Freeze the chosen `rektslug-glass` profile
- [ ] T013 Re-run the full matrix against Coinglass
- [ ] T014 Confirm the calibrated profile beats the default local profile on the majority of target metrics
- [ ] T015 Confirm CoinAnk-oriented and default profiles are unaffected

## Phase 5: Documentation

- [ ] T016 Document Coinglass-focused calibration commands
- [ ] T017 Record final acceptance metrics and profile identity
