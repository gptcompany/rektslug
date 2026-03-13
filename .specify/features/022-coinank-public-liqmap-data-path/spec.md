# Spec 022: CoinAnK Public Liq-Map Data Path

## Overview

Replace the current public CoinAnK-style liq-map route data path with a dedicated
backend calculation path that is structurally closer to CoinAnK.

The current public route renders correctly as HTML, but its underlying dataset is
still derived from the legacy local `/liquidations/levels` path. That path is
good enough for local OI-based inspection, but it does not reproduce CoinAnK's
price-grid structure, leverage ladder, split behavior, or cumulative curves.

## Scope

### In Scope

- define and implement a dedicated backend data path for the public CoinAnK-style liq-map route
- produce a CoinAnK-like price grid for `BTCUSDT` and `ETHUSDT`
- introduce a CoinAnK-like leverage ladder representation for public-route calculations
- compute long/short split and cumulative curves from the dedicated public dataset
- keep `1d` and `1w` as the only supported public parity targets

### Out of Scope

- generic local `/liquidations/levels` parity against providers
- Coinglass public-route parity
- `liq-heat-map` parity
- Counterflow / TradingView Lightweight work

## Architectural Decision

- keep `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}` as the public HTML URL
- add `GET /liquidations/coinank-public-map` as the dedicated backend payload endpoint
- keep legacy `/liquidations/levels` available for existing local workflows

## Functional Requirements

- **FR-001**: The public CoinAnK-style route MUST stop depending on the legacy local OI-bucket shape as its direct source of rendered bins.
- **FR-002**: The public data path MUST compute a CoinAnK-like price grid for `BTCUSDT` and `ETHUSDT` on `1d` and `1w`.
- **FR-003**: The public data path MUST compute long/short split and cumulative curves from the same dedicated dataset.
- **FR-004**: The public data path MUST expose enough leverage-ladder detail to support provider-like grouping.
- **FR-005**: The existing public HTML routes MUST remain stable.
- **FR-006**: The implementation MUST remain limited to `BTC/ETH x 1d/1w`.
- **FR-007**: The public route MUST be visually revalidated against CoinAnK after the backend rewrite.

## Frozen First-Pass Rules

- endpoint: `GET /liquidations/coinank-public-map`
- grid anchor: `current_price`
- grid snap: `anchor + round((raw - anchor) / step) * step`
- initial steps:
  - BTC `1d`: `10.0`
  - BTC `1w`: `25.0`
  - ETH `1d`: `0.5`
  - ETH `1w`: `2.0`

## Success Criteria

- **SC-001**: The public route for `BTCUSDT 1d` is no longer visually classified as “far” from CoinAnK by manual review.
- **SC-002**: The first structural rewrite pass achieves `>= 90` visual similarity on the public route, with `95` retained as the final parity target after tuning.
- **SC-003**: `BTC/ETH x 1d/1w` public-route validations produce distinct, timeframe-appropriate views rather than near-identical outputs.
