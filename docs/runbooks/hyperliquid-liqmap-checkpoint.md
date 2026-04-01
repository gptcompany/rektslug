# Hyperliquid Liq-Map Checkpoint

Date: 2026-04-01

## Scope

Checkpoint for the Hyperliquid liquidation-map track only.

This document covers:

- current `v1` UI status
- experimental `v2` route for future tests
- latest sidecar vs CoinGlass audits
- concrete next steps for a clean follow-up session

It does not cover unrelated ingestion or provider-comparison tracks.

## Current UI Routes

Primary `v1` routes:

- `http://10.0.0.2:8016/chart/derivatives/liq-map/hyperliquid/btcusdt/1w`
- `http://10.0.0.2:8016/chart/derivatives/liq-map/hyperliquid/ethusdt/1w`

Experimental `v2` routes:

- `http://10.0.0.2:8016/chart/derivatives/liq-map-v2/hyperliquid/btcusdt/1w`
- `http://10.0.0.2:8016/chart/derivatives/liq-map-v2/hyperliquid/ethusdt/1w`

The `v2` route was added so future experiments do not overwrite the current `v1`
experience. The current `v2` page still shares the same frontend file and is
only route-isolated plus visibly badged as experimental.

## Current Data Sources

Main sidecar cache used by `v1`:

- `data/cache/hl_sidecar_btcusdt.json`
- `data/cache/hl_sidecar_ethusdt.json`

Current API endpoint used by the UI:

- `/liquidations/hl-public-map?symbol=BTCUSDT&timeframe=1w`
- `/liquidations/hl-public-map?symbol=ETHUSDT&timeframe=1w`

CoinGlass comparison capture used in this checkpoint:

- `data/validation/raw_provider_api/20260320T183129Z`

Decoded CoinGlass Hyperliquid payload source:

- `api/hyperliquid/topPosition/liqMap?symbol=BTC`
- `api/hyperliquid/topPosition/liqMap?symbol=ETH`

## Confirmed UI Work

The following changes were already applied to the shared liq-map page:

- local Plotly asset instead of external CDN dependency
- visible in-page load error instead of silent blank chart
- restored Plotly modebar with navigation controls
- magnetic hover prototype using bucket-side snapping and cumulative anchor traces
- tooltip content now includes both `at level` and `cumulative` values

Relevant files:

- `frontend/liq_map_1w.html`
- `src/liquidationheatmap/api/main.py`

## Audit Artifacts

Main comparison artifacts:

- `data/validation/comparison_hl_btc_cache_canonical.json`
- `data/validation/comparison_hl_eth_cache_canonical.json`
- `data/validation/hl_coinglass_360_audit.json`
- `data/validation/hl_coinglass_mass_redistribution_report.json`
- `data/validation/hl_coinglass_mass_redistribution_report.md`

These are the files to read first in the next session.

## What Is Confirmed

### 1. CoinGlass Y-axis is not exact physical quantity

The public CoinGlass page text describes Y as relative liquidation intensity,
not exact contracts or exact coin count.

Reference:

- `data/validation/raw_provider_api/20260320T183129Z/coinglass/02_page.json`

### 2. CoinGlass Hyperliquid payload is top-position based

The decoded Hyperliquid payload used in this work is a list of positions with:

- `positionUsd`
- `size`
- `liquidationPrice`
- `userId`

This means the comparison path is:

- our full sidecar universe
- vs CoinGlass `topPosition` universe

This is a major source of divergence.

### 3. Divergence is not only scale

The latest audit shows both:

- mass differences
- redistribution differences across adjacent price bands

Examples from the latest report:

- `ETH long` mass ratio in USD: `1.187x`
- `ETH short` mass ratio in USD: `1.198x`
- `BTC long` mass ratio in USD: `1.258x`
- `BTC short` mass ratio in USD: `1.212x`

But local price-band mismatches are much larger than those global mass ratios.

### 4. ETH example around 1650 does not point mainly to current-price conversion

For `ETH long ~1650`, the measured cumulative values were:

- our `coin_bucket`: about `147.1k ETH`
- our `coin_current`: about `123.3k ETH`
- CoinGlass `coin_bucket`: about `112.7k ETH`
- CoinGlass `coin_current`: about `95.2k ETH`
- CoinGlass `coin_size`: about `95.1k ETH`

The bigger issue there is that our sidecar carries more USD mass in that zone
than the decoded CoinGlass payload.

## Current Interpretation

At this checkpoint, the most likely decomposition is:

`gap = universe mismatch + local redistribution mismatch + tail/display mismatch`

Not just:

`gap = wrong unit conversion`

The current working hypothesis is:

- `v1` is already valid as a truthful/internal Hyperliquid map
- matching CoinGlass more closely requires experiments, not replacing `v1`

## Best Next Experiment

Do not keep tuning `v1` directly.

The next decisive test is:

1. Build a `v2` backend/data variant from the same local CoinGlass
   `topPosition` capture universe
2. Compare `same universe` vs `full universe`
3. Only after that, revisit binning/clustering rules

If the gap collapses on `same universe`, the primary cause is universe coverage.

If the gap remains large, the primary cause is our binning / liquidation
allocation / aggregation logic.

## Commands To Resume

Start the local server:

```bash
uv run uvicorn src.liquidationheatmap.api.main:app --host 0.0.0.0 --port 8016
```

Open the current UI:

```bash
http://10.0.0.2:8016/chart/derivatives/liq-map/hyperliquid/ethusdt/1w
http://10.0.0.2:8016/chart/derivatives/liq-map/hyperliquid/btcusdt/1w
```

Open the experimental route:

```bash
http://10.0.0.2:8016/chart/derivatives/liq-map-v2/hyperliquid/ethusdt/1w
http://10.0.0.2:8016/chart/derivatives/liq-map-v2/hyperliquid/btcusdt/1w
```

Read the latest summary report:

```bash
sed -n '1,220p' data/validation/hl_coinglass_mass_redistribution_report.md
```

## Files Touched In This Session

Main files:

- `frontend/liq_map_1w.html`
- `src/liquidationheatmap/api/main.py`
- `src/liquidationheatmap/api/routers/liquidations.py`

Supporting artifacts:

- `data/validation/hl_coinglass_360_audit.json`
- `data/validation/hl_coinglass_mass_redistribution_report.json`
- `data/validation/hl_coinglass_mass_redistribution_report.md`

## Important Caveat

The working tree is dirty beyond this track. Do not assume every modified file in
`git status` belongs to the Hyperliquid liq-map work.

Resume from this checkpoint by treating `v1` as preserved and `v2` as the safe
place for future experiments.
