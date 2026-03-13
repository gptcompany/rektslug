# Spec-022 Baseline Audit

Date: 2026-03-13

## Scope Captured

Canonical public-route matrix audited for this spec:

- `/chart/derivatives/liq-map/binance/btcusdt/1d`
- `/chart/derivatives/liq-map/binance/btcusdt/1w`
- `/chart/derivatives/liq-map/binance/ethusdt/1d`
- `/chart/derivatives/liq-map/binance/ethusdt/1w`

This audit treats `spec-016` as historical frontend checklist only. The active gap
is the public/backend data path for the canonical CoinAnK-style route.

## Current Mismatch Evidence

### 1. Canonical public route still consumes legacy `/liquidations/levels`

Source evidence from `frontend/liq_map_1w.html`:

- canonical CoinAnK-style paths are detected from `window.location.pathname`
- `loadLevels()` builds `levelsUrl` against `/liquidations/levels`
- the fetch path is still `fetch(levelsUrl)`

This means the canonical public HTML route is still structurally tied to the
legacy OI-bucket payload.

### 2. Legacy payload shape is too compressed for CoinAnK-style parity

Source evidence from `src/liquidationheatmap/api/routers/liquidations.py`:

- `LiquidationLevelsResponse` exposes only:
  - `symbol`
  - `model`
  - `current_price`
  - `long_liquidations`
  - `short_liquidations`
- no explicit grid metadata
- no typed leverage ladder contract
- no server-computed cumulative series
- no freshness metadata for the public page

This forces the frontend to invent provider-like structure after the fact.

### 3. Public grouping is still too coarse

Source evidence from `frontend/liq_map_1w.html`:

- `rektslug-ank-public` currently groups only:
  - Low: `25x`
  - Medium: `50x`
  - High: `100x`

The frozen `spec-022` requirement is richer:

- preserved ladder before grouping:
  - `25x, 30x, 40x, 50x, 60x, 70x, 80x, 90x, 100x`
- first-pass grouping:
  - Low: `25x, 30x, 40x`
  - Medium: `50x, 60x, 70x`
  - High: `80x, 90x, 100x`

### 4. CDF and range are still frontend-derived

Source evidence from `frontend/liq_map_1w.html`:

- `computeDisplayRange(...)` calculates the visible X-range in the browser
- `calculateCumulative(...)` calculates cumulative long/short series in the browser

`spec-022` freezes these as server-side responsibilities of the `public liqmap builder`.

### 5. Existing public profile is not the source of truth for the frozen step table

Source evidence from `src/liquidationheatmap/models/profiles.py`:

- `rektslug-ank-public` currently overrides:
  - BTC `1d` -> `10.0`
  - BTC `1w` -> `12.0`
  - ETH `1d` -> `0.45`
  - ETH `1w` -> `1.65`

Frozen `spec-022` step table:

- BTC `1d` -> `10.0`
- BTC `1w` -> `25.0`
- ETH `1d` -> `0.5`
- ETH `1w` -> `2.0`

So the public route cannot simply inherit the current profile bin-size overrides.

## Architectural Decision Frozen In Branch

The implementation contract for this spec is frozen as:

- keep public HTML URL stable:
  - `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}`
- add dedicated backend endpoint:
  - `GET /liquidations/coinank-public-map`
- implement a dedicated `public liqmap builder`
- make `frontend/liq_map_1w.html` consume the new endpoint on canonical public routes
- keep legacy `/liquidations/levels` available and regression-tested

## Immediate Phase-2 Test Targets

The RED suite must lock the following before backend rewrite:

- typed public builder schema/contract
- symbol/timeframe-aware grid generation
- richer leverage ladder preservation
- cumulative anchoring at `current_price`
- canonical frontend switch to `/liquidations/coinank-public-map`
- legacy `/liquidations/levels` regression coverage
- explicit builder failure contract
- distinct BTC vs ETH and `1d` vs `1w` behavior
