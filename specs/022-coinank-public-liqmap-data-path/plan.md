# Implementation Plan: CoinAnK Public Liq-Map Data Path

## Summary

Build a dedicated backend calculation path for the public CoinAnK-style liq-map
route, then revalidate the public route visually against CoinAnK on
`BTC/ETH x 1d/1w`.

## Technical Context

### Existing Infrastructure

| Component | Status | Notes |
|----------|--------|-------|
| Public route HTML | Exists | `frontend/liq_map_1w.html` served under `/chart/derivatives/liq-map/...` |
| Legacy local levels path | Exists | Good for local OI inspection, not provider-equivalent |
| CoinAnK comparison harness | Exists | `spec-017`, `spec-018`, `spec-020` already provide artifacts and validator tooling |
| Public profile split | Exists | `rektslug-ank-public` is already separated from `rektslug-ank` |
| Visual validation tooling | Exists | `scripts/validate_liqmap_visual.py`, `scripts/run_visual_harness.py` |

### Required Environment

- `rektslug-api` healthy on `:8002`
- `rektslug-sync` running
- DuckDB readable and not in conflicting configuration state
- Playwright/Chromium available for visual validation
- CoinAnK credentials available via `dotenvx`

### Reference URLs

- Public route:
  - `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
  - `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
  - `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
  - `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- Template:
  - `http://localhost:8002/frontend/liq_map_1w.html`

## Working Assumption

The current public route is structurally wrong because it derives provider-like
visuals from the wrong backend dataset. The fix should happen in backend data
generation first, not as another frontend-only tweak pass.

## Architecture

### Desired Flow

```text
DuckDB / local model inputs
  -> dedicated CoinAnK-style public builder
  -> public-route payload with provider-like grid / ladder / cumulative data
  -> frontend/liq_map_1w.html
  -> validate_liqmap_visual.py / run_visual_harness.py
```

### Candidate Implementation Shape

- keep the public URL contract unchanged
- add a dedicated builder/helper in the API layer or db service for public CoinAnK-style liq-map data
- keep legacy `/liquidations/levels` available for existing local workflows if needed
- route public CoinAnK-style pages through the dedicated path, not through blind reuse of legacy grouped output

## What Already Works

- HTML route serving and deploy path
- public profile separation (`rektslug-ank-public`)
- local/CoinAnK visual harness and validation tooling
- provider comparison artifacts from `spec-017`

## What Needs Work

1. Dedicated public data builder
2. Symbol-aware / timeframe-aware grid generation
3. Provider-like leverage ladder representation
4. Cumulative calculation from the dedicated public dataset
5. Revalidation of the public route on `BTC/ETH x 1d/1w`

## Phases

### Phase 1: Baseline & Contract

- capture the current public-route mismatch for `BTC 1d/1w` and `ETH 1d/1w`
- define the dedicated public payload contract
- decide whether the implementation lands as a new endpoint or internal builder

### Phase 2: RED Tests

- add tests for the new public-route builder
- add tests for symbol/timeframe-aware grid behavior
- add tests for cumulative anchoring and richer ladder preservation

### Phase 3: Backend Rewrite

- implement the dedicated public builder
- thread it into the canonical public route
- preserve backward-compatible HTML URLs

### Phase 4: Validation

- run public-route visual validation for `BTC/ETH x 1d/1w`
- compare against CoinAnK using the public route, not a private worktree-only path
- confirm route outputs are materially distinct between `1d` and `1w`

### Phase 5: Documentation

- document the public-route backend contract
- document how this spec supersedes the remaining backend/data-path gap in `spec-016`

## Risks

- backend rewrite may surface more DuckDB contention or latency
- provider-like grid approximation may still need one tuning pass after structural rewrite
- frontend assumptions may need small adjustments once the payload shape becomes richer

## Quickstart

```bash
# health
curl -fsS http://localhost:8002/health

# public route validation
uv run python scripts/validate_liqmap_visual.py --exchange binance --coin BTC --coinank-timeframe 1d

# harness validation
uv run python scripts/run_visual_harness.py \
  --provider coinank \
  --product liq-map \
  --renderer plotly \
  --symbol BTCUSDT \
  --timeframe 1d \
  --api-base http://127.0.0.1:8002 \
  --pass-threshold 95
```
