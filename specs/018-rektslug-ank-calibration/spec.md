# Spec 018: Rektslug-Ank Calibration

## Overview

Calibrate a dedicated `rektslug-ank` profile for the local `liq-map` model so the
output aligns more closely with CoinAnK without replacing the existing default
local profile.

This spec is model-calibration work, not visual harness work:

- `spec-017` closed the `liq-map` provider-comparison infrastructure
- `spec-018` uses that infrastructure to tune `rektslug` specifically against CoinAnK

## Reference Sources

The repo files below are the working source of truth for this spec:

- `specs/017-liqmap-provider-comparison/spec.md`
- `specs/017-liqmap-provider-comparison/plan.md`
- `docs/provider-api-comparison.md`
- `docs/runbooks/chart-routes.md`
- `scripts/run_provider_api_comparison.py`
- `scripts/capture_provider_api.py`
- `scripts/compare_provider_liquidations.py`
- `scripts/provider_gap_analysis.py`
- `scripts/coinank_screenshot.py`
- `scripts/validate_liqmap_visual.py`

## Scope

### In Scope

- product: `liq-map` only
- target provider: CoinAnK only
- symbols: `BTCUSDT`, `ETHUSDT`
- timeframes: `1d`, `1w`
- bucket sizing, scaling, leverage grouping, range selection, and profile metadata
- explicit local profile selection for `rektslug-ank`

### Out of Scope

- Coinglass-specific calibration
- `liq-heat-map`
- generic screenshot scoring infrastructure
- Counterflow integration

## Reference URLs

- Local BTC 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- Local BTC 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local ETH 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- Local ETH 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- CoinAnK BTC 1D: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d`
- CoinAnK BTC 1W: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- CoinAnK ETH 1D: `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1d`
- CoinAnK ETH 1W: `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1w`

## Tooling Assumptions

- `uv` project environment is available
- Playwright/Chromium is already usable where screenshot spot-checks are needed
- provider secrets continue to be loaded via `dotenvx`, especially:
  - `COINANK_USER`
  - `COINANK_PASSWORD`

## Problem Statement

`spec-017` proved that local `rektslug`, CoinAnK, and Coinglass can be compared
reliably. It also showed that the local model is structurally compatible with both
providers but not numerically aligned 1:1 with either.

For CoinAnK specifically, the local model needs a provider-oriented calibration pass
instead of a single compromise profile shared by all vendors.

## Functional Requirements

- **FR-001**: The repo MUST expose an explicit `rektslug-ank` calibration profile for `liq-map`.
  - *AC*: Profile selectable via `--profile rektslug-ank` (or equivalent config key) in the comparison workflow.
- **FR-002**: Calibration MUST use the same `BTC/ETH x 1d/1w` matrix already frozen by `spec-017`.
  - *AC*: Calibration runs cover exactly 4 entries: `BTCUSDT 1d`, `BTCUSDT 1w`, `ETHUSDT 1d`, `ETHUSDT 1w`.
- **FR-003**: Calibration MUST optimize against CoinAnK artifacts only.
  - *AC*: No Coinglass or Counterflow data used as optimization target during calibration.
- **FR-004**: Calibration runs MUST preserve machine-readable reports describing the chosen profile parameters and resulting gap metrics.
  - *AC*: Each run emits a JSON report in `data/validation/provider_comparisons/` containing profile name, parameters, and per-metric gap values.
- **FR-005**: The local comparison workflow MUST be able to select the calibrated profile without breaking the default local profile.
  - *AC*: Running the comparison with `rektslug-default` after calibration produces identical results to pre-calibration baseline.
- **FR-006**: Calibration acceptance MUST be based on measurable parity metrics, not visual inspection alone.
  - *AC*: Acceptance decision derives from the 5 core metrics defined in Calibration Targets, with improvement-based thresholds.
- **FR-007**: The resulting profile metadata MUST be explicit enough to tell whether a run used `rektslug-default` or `rektslug-ank`.
  - *AC*: Every report and manifest includes a `profile` field with the active profile name.

## Calibration Targets

Primary metrics to improve (improvement-based, not absolute):

| # | Metric | Definition | Improvement threshold |
|---|--------|------------|-----------------------|
| 1 | bucket-count proximity | `abs(local_buckets - provider_buckets) / provider_buckets` | Reduce gap vs baseline by >= 20% |
| 2 | long/short total ratio | `abs(local_ls_ratio - provider_ls_ratio)` | Reduce gap vs baseline by >= 15% |
| 3 | long/short peak ratio | `abs(local_peak_ratio - provider_peak_ratio)` | Reduce gap vs baseline by >= 15% |
| 4 | current-price anchor | `abs(local_anchor - provider_anchor) / provider_anchor` | Reduce gap vs baseline by >= 10% |
| 5 | bucket overlap | `intersection(rebin(local_buckets, aligned_step), rebin(provider_buckets, aligned_step)) / union(...)` | Increase overlap vs baseline by >= 10% |

Acceptance rule: the calibrated profile MUST improve **at least 3 out of 5**
metrics on **at least 3 out of 4** matrix entries, without critical regression
(> 30% degradation) on any entry.

## Non-Functional Requirements

- **NFR-001**: A single calibration run (4 matrix entries) MUST complete in < 10 minutes on the development workstation.
- **NFR-002**: Calibration reports MUST be < 1 MB each and stored as JSON.
- **NFR-003**: Profile selection MUST NOT change any behavior when `rektslug-default` is active (full backward compatibility).

## Edge Cases

- **EC-001**: CoinAnK is unreachable during calibration — calibration MUST abort cleanly, not produce partial results.
- **EC-002**: Calibration improves BTC but degrades ETH beyond 30% — the candidate MUST be rejected per the acceptance rule.
- **EC-003**: No candidate improves 3/5 metrics on 3/4 entries — calibration concludes as "no improvement found", the default profile is preserved, and the failure is documented in a JSON report.
- **EC-004**: CoinAnK data changes between calibration runs (provider drift) — reports MUST include capture timestamps to allow drift detection.

## Success Criteria

- **SC-001**: A `rektslug-ank` profile exists and can be selected in the comparison workflow.
- **SC-002**: On the `BTC/ETH x 1d/1w` matrix, the calibrated profile improves at least 3 out of 5 core metrics on at least 3 out of 4 matrix entries, without critical regression (> 30% degradation) on any entry.
- **SC-003**: The profile can be reproduced from versioned config and artifact history, not ad-hoc local tuning.
- **SC-004**: CoinAnK-focused calibration does not silently overwrite or redefine the default local profile.

## Notes

- `spec-019` will do the same for Coinglass.
- `spec-020` will handle visual comparison harness concerns separately.
