# Spec 022: CoinAnK Public Liq-Map Data Path

## Overview

Replace the current public CoinAnK-style liq-map route data path with a dedicated
backend calculation path that is structurally closer to CoinAnK.

The current public route renders correctly as HTML, but its underlying dataset is
still derived from the legacy local `/liquidations/levels` path. That path is
good enough for local OI-based inspection, but it does not reproduce CoinAnK's
price-grid structure, leverage ladder, split behavior, or cumulative curves.

This spec is specifically about the **public CoinAnK-style liq-map route**:

- `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}`
- `frontend/liq_map_1w.html`
- the backend payload feeding that page

It is not a generic visual tweak spec.

## Reference Sources

- `specs/016-liqmap-1to1-coinank/spec.md`
- `specs/017-liqmap-provider-comparison/spec.md`
- `specs/018-rektslug-ank-calibration/spec.md`
- `specs/020-visual-comparison-harness/spec.md`
- `docs/provider-api-comparison.md`
- `docs/runbooks/chart-routes.md`
- `docs/runbooks/parity-thresholds.md`
- `scripts/compare_provider_liquidations.py`
- `scripts/run_provider_api_comparison.py`
- `scripts/run_visual_harness.py`
- `scripts/validate_liqmap_visual.py`
- `src/liquidationheatmap/api/routers/liquidations.py`
- `src/liquidationheatmap/ingestion/db_service.py`
- `src/liquidationheatmap/models/profiles.py`
- `frontend/liq_map_1w.html`

## Problem Statement

The public CoinAnK-style route is still far from CoinAnK on:

- left Y-axis magnitudes
- bin size and bin placement
- cumulative distribution shape
- long/short split around current price
- leverage-group composition

The main reason is architectural: the page still consumes a local OI-bucket
dataset that is only later grouped visually, while CoinAnK's `liq-map` behaves
like a provider-specific grid/ladder product.

## Scope

### In Scope

- define and implement a dedicated backend data path for the public CoinAnK-style liq-map route
- produce a CoinAnK-like price grid for `BTCUSDT` and `ETHUSDT`
- introduce a CoinAnK-like leverage ladder representation for public-route calculations
- compute long/short split and cumulative curves from the dedicated public dataset
- keep `1d` and `1w` as the only supported public parity targets
- preserve the existing public HTML route contract
- validate `rektslug vs CoinAnK` visually on the public route

### Out of Scope

- generic local `/liquidations/levels` parity against providers
- Coinglass public-route parity
- `liq-heat-map` parity
- Counterflow / TradingView Lightweight work
- redesigning the Plotly page visual language from scratch

## Reference URLs

- Local public route:
  - `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
  - `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
  - `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
  - `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- Local template:
  - `http://localhost:8002/frontend/liq_map_1w.html`
- CoinAnK reference page / capture flow:
  - `scripts/coinank_screenshot.py`
  - existing URLs and credentials documented in repo / `dotenvx`

## Tooling Assumptions

- Playwright/Chromium remain the canonical visual validation tooling.
- The public-route validator remains `scripts/validate_liqmap_visual.py`.
- `scripts/run_visual_harness.py` remains the canonical screenshot/score runner.
- The public-route rewrite should remain compatible with `rektslug-ank-public`.

## Functional Requirements

- **FR-001**: The public CoinAnK-style route MUST stop depending on the legacy local OI-bucket shape as its direct source of rendered bins.
  - Acceptance: the public route uses a dedicated backend builder or endpoint for CoinAnK-style liq-map payloads.
- **FR-002**: The public data path MUST compute a CoinAnK-like price grid for `BTCUSDT` and `ETHUSDT` on `1d` and `1w`.
  - Acceptance: bin step and bin placement are derived from the dedicated public grid logic, not only from frontend grouping.
- **FR-003**: The public data path MUST compute long/short split and cumulative curves from the same dedicated dataset.
  - Acceptance: cumulative curves are generated from the public-route dataset and anchor correctly at current price.
- **FR-004**: The public data path MUST expose enough leverage-ladder detail to support provider-like grouping.
  - Acceptance: the backend payload preserves a richer ladder than a hardcoded three-bucket approximation before frontend grouping.
- **FR-005**: The existing public HTML routes MUST remain stable.
  - Acceptance: `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}` remains the user-facing URL.
- **FR-006**: The implementation MUST remain limited to `BTC/ETH x 1d/1w`.
  - Acceptance: unsupported symbols/timeframes fail fast or clearly fall back outside the parity path.
- **FR-007**: The public route MUST be visually revalidated against CoinAnK after the backend rewrite.
  - Acceptance: validation artifacts are generated for `BTC/ETH x 1d/1w` using the public route, not a worktree-only private path.

## Data-Path Contract

The dedicated public CoinAnK-style data path should expose, directly or via an
internal builder, enough information to render:

- current price / pivot price
- ordered price buckets on a CoinAnK-like grid
- long-side values per leverage bucket
- short-side values per leverage bucket
- grouped outputs for `Low / Medium / High`
- cumulative long / cumulative short series derived from those buckets

The page should not have to invent the provider-like structure from a compressed
legacy response.

## Non-Functional Requirements

- **NFR-001**: A single public-route visual validation run (`BTC 1d`) MUST complete in `< 120s`.
- **NFR-002**: Public-route payload generation MUST not fall back to the synthetic 5-level dataset when real DuckDB-backed public data is available.
- **NFR-003**: The public-route implementation MUST preserve backward-compatible URLs and return valid HTML for the existing chart routes.
- **NFR-004**: Validation artifacts for one route pair MUST remain `< 1 MB` each for manifest and score outputs.

## Edge Cases

- **EC-001**: DuckDB data is stale but non-empty.
  - Expected: use stale real data with explicit metadata rather than synthetic fallback.
- **EC-002**: Public route is available but the dedicated data-path builder fails.
  - Expected: fail explicitly and diagnostically; do not silently collapse to a misleading near-empty chart.
- **EC-003**: BTC and ETH require different grid scales.
  - Expected: the builder supports symbol-aware grid generation rather than one universal bucket step.
- **EC-004**: `1d` and `1w` require materially different visual ranges.
  - Expected: the builder or payload includes timeframe-aware range information.

## Success Criteria

- **SC-001**: The public route for `BTCUSDT 1d` is no longer visually classified as “far” from CoinAnK by manual review.
- **SC-002**: The public-route visual harness achieves at least the visual threshold documented for `liq-map` parity, with `95` as the official target and `90` as the minimum diagnostic threshold.
- **SC-003**: `BTC/ETH x 1d/1w` public-route validations produce distinct, timeframe-appropriate views rather than near-identical outputs.
- **SC-004**: The public-route backend contract is documented well enough that future CoinAnK public tuning does not require more blind frontend-only tweaks.

## Related Specs

- `spec-016`: original CoinAnK visual parity spec; now partially superseded by this backend/public-route rewrite
- `spec-017`: provider comparison harness for liq-map datasets
- `spec-018`: CoinAnK-oriented calibration profile
- `spec-020`: visual harness and screenshot/score contract
