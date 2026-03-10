# Tasks: Rektslug-Ank Calibration

**Input**: `specs/018-rektslug-ank-calibration/spec.md`
**Dependencies**: `spec-017` comparison artifacts and workflow
**Feature Type**: Model calibration profile

## Phase 1: Baseline Audit

- [X] T001 Collect the current `spec-017` CoinAnk comparison metrics for `BTC/ETH x 1d/1w`
- [X] T002 Define the exact metric set and acceptance thresholds for `rektslug-ank`
- [X] T003 [P] Identify which local parameters are allowed to vary (bin size, weighting, scaling, grouping, range)

## Phase 2: Profile Surface

> **TDD order**: T004 writes failing tests first, T005-T006 implement to make them pass.

- [X] T004 Write failing tests that assert profile selection (`rektslug-default` vs `rektslug-ank`) and manifest profile recording
- [X] T005 Introduce an explicit `rektslug-ank` profile/config surface in the local workflow (GREEN for T004 tests)
- [X] T006 Ensure manifests/reports record the active local profile name (GREEN for T004 manifest tests)

## Phase 3: Calibration Loop

> **TDD note**: T007-T010 are parameter-sweep experiments (vary bin size, weighting,
> scaling, grouping, range per T003 inventory). TDD applies only if new calibration
> code is introduced; pure config changes are validated by T011/T014 assertions.

- [X] T006c Implement graceful abort when CoinAnK is unreachable during calibration (EC-001): no partial results, clean exit with error report
- [X] T007 Run parameter-sweep calibration on BTC 1D (vary parameters from T003; compare via `compare_provider_liquidations.py`)
- [X] T008 Run parameter-sweep calibration on BTC 1W
- [X] T009 Run parameter-sweep calibration on ETH 1D
- [X] T010 Run parameter-sweep calibration on ETH 1W
- [X] T011 Compare each candidate against the original local baseline using the acceptance rule (3/5 metrics on 3/4 entries) and retain only improving changes
- [X] T011b If no candidate meets the acceptance rule, preserve the default profile and document the failure in a JSON report

## Phase 4: Validation

- [X] T012 Freeze the chosen `rektslug-ank` profile parameters in versioned config/code
- [X] T013 Re-run the full `BTC/ETH x 1d/1w` matrix against CoinAnk and verify: wall-clock runtime < 10 min (NFR-001), each report is stored as JSON and remains < 1 MB (NFR-002), capture timestamps present in every report (EC-004)
- [X] T014 Confirm the calibrated profile improves at least `3/5` core metrics on at least `3/4` matrix entries, with no critical regression (> 30% degradation vs `rektslug-default` baseline) on any entry
- [X] T015 Confirm the default local profile still works unchanged when selected explicitly

## Phase 5: Documentation

- [X] T016 Document how to run CoinAnk-focused calibration and comparison
- [X] T017 Record the final acceptance metrics and profile identity in artifacts/spec notes

## Completion Notes

- Accepted calibration artifact: `data/validation/provider_comparisons/20260310T235617Z_calibration_rektslug-ank.json`
- Acceptance result: `accepted`, `4/4` matrix entries passing, `0` critical regressions
- Runtime gate: `114.6s` total wall-clock, below `NFR-001` (`< 10 min`)
