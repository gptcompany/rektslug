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
- **FR-002**: Calibration MUST use the same `BTC/ETH x 1d/1w` matrix already frozen by `spec-017`.
- **FR-003**: Calibration MUST optimize against CoinAnK artifacts only.
- **FR-004**: Calibration runs MUST preserve machine-readable reports describing the chosen profile parameters and resulting gap metrics.
- **FR-005**: The local comparison workflow MUST be able to select the calibrated profile without breaking the default local profile.
- **FR-006**: Calibration acceptance MUST be based on measurable parity metrics, not visual inspection alone.
- **FR-007**: The resulting profile metadata MUST be explicit enough to tell whether a run used `rektslug-default` or `rektslug-ank`.

## Calibration Targets

Primary metrics to improve:

- bucket-count proximity
- long/short total ratio proximity
- long/short peak ratio proximity
- current-price anchor distance
- overlap on common price buckets

The exact thresholds belong in the plan/tasks, but the direction is strict:
`rektslug-ank` must move materially closer to CoinAnK than the current generic
profile.

## Success Criteria

- **SC-001**: A `rektslug-ank` profile exists and can be selected in the comparison workflow.
- **SC-002**: On the `BTC/ETH x 1d/1w` matrix, the calibrated profile improves parity against CoinAnK relative to the default local profile on the majority of core metrics.
- **SC-003**: The profile can be reproduced from versioned config and artifact history, not ad-hoc local tuning.
- **SC-004**: CoinAnK-focused calibration does not silently overwrite or redefine the default local profile.

## Notes

- `spec-019` will do the same for Coinglass.
- `spec-020` will handle visual comparison harness concerns separately.
