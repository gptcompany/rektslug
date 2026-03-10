# Spec 019: Rektslug-Glass Calibration

## Overview

Calibrate a dedicated `rektslug-glass` profile for the local `liq-map` model so
the output aligns more closely with Coinglass while remaining independent from
the CoinAnK-oriented profile.

## Reference Sources

- `specs/017-liqmap-provider-comparison/spec.md`
- `specs/017-liqmap-provider-comparison/plan.md`
- `docs/provider-api-comparison.md`
- `docs/provider-api-handoff.md`
- `docs/runbooks/chart-routes.md`
- `scripts/run_provider_api_comparison.py`
- `scripts/capture_provider_api.py`
- `scripts/compare_provider_liquidations.py`
- `scripts/provider_gap_analysis.py`
- `scripts/coinglass_bundle_report.py`
- `scripts/coinglass_decode_payload.js`

## Scope

### In Scope

- product: `liq-map` only
- target provider: Coinglass only
- symbols: `BTCUSDT`, `ETHUSDT`
- timeframes: `1d`, `1w`
- profile metadata, range mapping, bucket shaping, scaling, and clustering decisions

### Out of Scope

- CoinAnK calibration
- `liq-heat-map`
- screenshot scoring infrastructure
- Counterflow integration

## Reference URLs

- Local BTC 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- Local BTC 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local ETH 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- Local ETH 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- Coinglass page: `https://www.coinglass.com/pro/futures/LiquidationMap`
- Coinglass API: `https://capi.coinglass.com/api/index/5/liqMap`

## Tooling Assumptions

- `uv` project environment is available
- Coinglass REST/browser capture paths from `spec-017` remain usable
- provider secrets continue to be loaded via `dotenvx`, especially:
  - `COINGLASS_USER_LOGIN`
  - `COINGLASS_USER_PASSWORD`
  - `COINGLASS_APP_BUNDLE` (optional but useful)

## Functional Requirements

- **FR-001**: The repo MUST expose an explicit `rektslug-glass` calibration profile for `liq-map`.
- **FR-002**: Calibration MUST optimize against Coinglass-only artifacts from the existing comparison workflow.
- **FR-003**: The calibrated profile MUST be selectable without replacing `rektslug-default` or `rektslug-ank`.
- **FR-004**: Reports MUST record which local profile generated the local dataset.
- **FR-005**: Acceptance MUST use measurable parity metrics derived from the comparison harness.

## Success Criteria

- **SC-001**: `rektslug-glass` can be selected as a first-class local profile.
- **SC-002**: It improves Coinglass parity over the default profile on the majority of core metrics across `BTC/ETH x 1d/1w`.
- **SC-003**: CoinAnK-focused calibration remains isolated from Coinglass-focused calibration.

## Notes

- `spec-018` and `spec-019` are parallel by concept but should be executed independently.
- `spec-020` will standardize visual comparison on top of these profiles.
