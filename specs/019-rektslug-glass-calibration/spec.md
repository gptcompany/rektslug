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
- **FR-003**: Calibration MUST compare a fresh local baseline (`rektslug-default`) and the calibrated local profile against the same frozen Coinglass reference per matrix entry.
- **FR-004**: The calibrated profile MUST be selectable without replacing `rektslug-default` or `rektslug-ank`.
- **FR-005**: Reports MUST record which local profile generated the local dataset.
- **FR-006**: Acceptance MUST use measurable parity metrics derived from the comparison harness.

## Calibration Targets

Primary metrics to improve (improvement-based, not absolute):

| # | Metric | Definition | Improvement threshold |
|---|--------|------------|-----------------------|
| 1 | bucket-count proximity | `abs(local_buckets - provider_buckets) / provider_buckets` | Reduce gap vs baseline by >= 20% |
| 2 | long/short total ratio | `abs(local_ls_ratio - provider_ls_ratio)` | Reduce gap vs baseline by >= 15% |
| 3 | long/short peak ratio | `abs(local_peak_ratio - provider_peak_ratio)` | Reduce gap vs baseline by >= 15% |
| 4 | current-price anchor | `abs(local_anchor - provider_anchor) / provider_anchor` | Reduce gap vs baseline by >= 10% |
| 5 | bucket overlap | `intersection(rebin(local_buckets, aligned_step), rebin(provider_buckets, aligned_step)) / union(...)` | Increase overlap vs baseline by >= 5% |

Coinglass-specific note: `liqMap` clusters liquidation state under top-level price
bucket keys, so aligned-grid `bucket_overlap` moves in smaller steps than the
CoinAnK-oriented profile. `spec-019` therefore uses a `>= 5%` improvement gate
for overlap while keeping the `3/5 on 3/4` acceptance rule unchanged.

Acceptance rule: the calibrated profile MUST improve **at least 3 out of 5**
metrics on **at least 3 out of 4** matrix entries, without critical regression
(> 30% degradation) on any entry.

## Success Criteria

- **SC-001**: `rektslug-glass` can be selected as a first-class local profile.
- **SC-002**: It improves at least `3/5` core metrics on at least `3/4` matrix entries, with no critical regression.
- **SC-003**: CoinAnK-focused calibration remains isolated from Coinglass-focused calibration.

## Notes

- `spec-018` should introduce the reusable local profile-surface mechanism first.
- `spec-019` should reuse that mechanism rather than reinventing profile plumbing.
- `spec-020` will standardize visual comparison on top of these profiles.
