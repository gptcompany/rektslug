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

Experimental `v3` routes:

- `http://10.0.0.2:8016/chart/derivatives/liq-map-v3/hyperliquid/btcusdt/1w`
- `http://10.0.0.2:8016/chart/derivatives/liq-map-v3/hyperliquid/ethusdt/1w`

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

Latest CoinGlass comparison capture used in this checkpoint:

- `data/validation/raw_provider_api/20260401T160752Z`

Older reference capture kept for drift comparison:

- `data/validation/raw_provider_api/20260320T183129Z`

Decoded CoinGlass Hyperliquid payload source:

- `api/hyperliquid/topPosition/liqMap?symbol=BTC`
- `api/hyperliquid/topPosition/liqMap?symbol=ETH`

## Confirmed UI Work

The following changes were already applied to the shared liq-map page:

- shared Plotly CDN dependency instead of `/node_modules` runtime coupling
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

## New Required Task Before Live CoinGlass Comparison

Before comparing `v2` against the live CoinGlass page on `2026-04-01`, refresh
the local Hyperliquid `topPosition/liqMap` capture.

Why this is required:

- current `v2` does **not** fetch live CoinGlass data
- `v2` resolves the latest matching local capture under
  `data/validation/raw_provider_api`
- at this checkpoint, the latest local Hyperliquid `topPosition/liqMap` capture
  is still `20260320T183129Z` (`2026-03-20 18:31:29Z`)

This means any visual comparison between `v2` and the live CoinGlass site mixes:

- universe/bucketing differences
- plus a `12`-day snapshot drift

Treat this as a blocking task for the next session:

1. capture a fresh CoinGlass Hyperliquid `topPosition/liqMap` snapshot
2. confirm `v2` resolves that newer local capture
3. only then compare `v2` vs live CoinGlass on bucket shape, cumulative curves,
   and display range

## 2026-04-01 Follow-up Verification

Fresh local captures were created on `2026-04-01`:

- BTC: `data/validation/raw_provider_api/20260401T160149Z`
- BTC + ETH: `data/validation/raw_provider_api/20260401T160752Z`

After the refresh, `v2` resolves:

- BTC -> `data/validation/raw_provider_api/20260401T160752Z`
- ETH -> `data/validation/raw_provider_api/20260401T160752Z`

Verified correspondence against the decoded local CoinGlass payload:

- `current_price`: exact match
- long buckets: exact match
- short buckets: exact match
- `cumulative_long`: exact match
- `cumulative_short`: exact match

Important nuance:

- the visible display range in `v2` is still inherited from the local sidecar
  grid, not from a CoinGlass-provided page viewport/range contract

So `v2` is now exact for the captured liquidation payload itself, but a
remaining live-page visual difference can still come from range/window choices.

This means the current `v2` path is confirmed as:

`CoinGlass topPosition replay inside our app`

not:

`our independent Hyperliquid model that happens to resemble CoinGlass`

## 2026-04-01 Runtime And Deploy Hardening

Two operational issues were confirmed and fixed on `2026-04-01`.

### Hyperliquid mirror compatibility

Local/VPS Hyperliquid info mirrors support:

- `meta`
- `userAbstraction`
- `clearinghouseState`

They do not support:

- `metaAndAssetCtxs`
- `allMids`

The `v3` precompute path now requests `meta` instead of
`metaAndAssetCtxs`, and fills mark prices from the existing sidecar state.
This keeps metadata lookup on the mirror-supported path instead of falling
back to `https://api.hyperliquid.xyz/info`.

### Container startup safety

The production image does not include `node_modules`.

The API previously mounted `/node_modules` unconditionally, which made the
container fail during FastAPI startup with:

- `RuntimeError: Directory 'node_modules' does not exist`

This is now hardened as follows:

1. `frontend/liq_map_1w.html` uses the same Plotly CDN as the other frontend
   pages
2. `src/liquidationheatmap/api/main.py` mounts `/node_modules` only when the
   directory actually exists

This removes the deploy-time startup dependency on `node_modules` while keeping
local development compatible when the directory is present.

## What This Means For V3

`v3` should not depend on CoinGlass captures.

To build a real internal replacement that can converge toward the same visual
shape, the likely requirements are:

1. Build a local `top-position-like` universe directly from Hyperliquid data
   rather than using the full sidecar universe.
2. Rank/select positions with a deterministic rule close to the CoinGlass
   population shape:
   `top N positions by notional / risk`, not all accounts.
3. Stop treating the comparison path as a diffuse risk-surface first.
   CoinGlass `topPosition` behaves like a list of positions with one main
   liquidation price per position, then bucketization.
4. Use live per-position liquidation prices where available.
   Existing BTC enrichment artifacts already showed that direct user/API
   enrichment materially improved correspondence versus older local estimates.
5. Keep `v1` intact as the full-universe internal truth.
   `v3` should be a separate model/product path, not a rewrite of `v1`.
6. Compare `v3` against the current `v2` replay path as the local acceptance
   test until CoinGlass dependency can be removed from evaluation.

## Concrete V3 Task List

1. Define a local `top-position` projector from Hyperliquid direct data
   (`hyperliquid-node` / direct snapshots), outputting one record per selected
   position with:
   - user
   - symbol
   - side
   - size
   - position USD
   - liquidation price
2. Decide and freeze the selection rule:
   - top positions by absolute notional
   - whether selection is global or per side
   - maximum population size
3. Reuse the existing public map contract and bucketizer on top of that local
   projected universe.
4. Validate local projected universe vs `v2` replay on BTC and ETH:
   - bucket counts
   - mass ratios
   - top band overlaps
   - cumulative curve error
5. Only after universe parity is acceptable, revisit residual differences in
   display range or bucket rounding.

## Live Enrichment Hardening

The `v3` precompute path no longer fires one unbounded `gather` over every
selected user.

As of `2026-04-01`, the live enrichment path now:

1. processes selected users in configurable chunks
2. caches per-user per-coin live overrides in
   `data/cache/hl_live_enrichment_cache.json`
3. reuses cached overrides for the configured TTL before calling Hyperliquid
   again
4. logs the configured Hyperliquid info endpoints and warns when only the
   public endpoint is active

Relevant env knobs:

- `HEATMAP_HYPERLIQUID_INFO_FALLBACK_URLS`
- `HEATMAP_HL_TOP_POSITION_SELECTION_MODE`
- `HEATMAP_HL_LIVE_ENRICH_TOP_N`
- `HEATMAP_HL_LIVE_ENRICH_RPM`
- `HEATMAP_HL_LIVE_ENRICH_BATCH_SIZE`
- `HEATMAP_HL_LIVE_ENRICH_CACHE_TTL_SECONDS`

Operational checklist before resuming `v3` tuning:

1. confirm the process actually loads `HEATMAP_HYPERLIQUID_INFO_FALLBACK_URLS`
   so local/VPS mirrors are preferred over `https://api.hyperliquid.xyz/info`
2. watch the live enrichment logs for:
   - configured endpoints
   - chunk counts
   - cached vs fetched users
3. only then raise `HEATMAP_HL_LIVE_ENRICH_TOP_N` or tune selection logic for
   BTC shape matching

## Immediate Next V3 Task

The global-vs-per-side selection comparison is now complete.

Observed result on `2026-04-01`:

- BTC combined `pearson_r`: `0.25` (`global`) vs `0.2506` (`per_side`)
- ETH combined `pearson_r`: `0.3061` (`global`) vs `0.3048` (`per_side`)

Conclusion:

- `per_side` helps long/short balance on ETH
- `per_side` does not materially improve the BTC shape mismatch
- the next `v3` gain will not come from ranking mode alone

Do next:

1. extend live enrichment coverage beyond the current small top subset
2. move from a `top users` heuristic toward a true `top positions` projector
3. keep the same bucketizer/public payload contract
4. measure again against `v2` with:
   - `pearson_r`
   - side-specific `pearson_r`
   - mass ratio
   - long-side BTC band overlap

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
http://10.0.0.2:8016/chart/derivatives/liq-map-v3/hyperliquid/ethusdt/1w
http://10.0.0.2:8016/chart/derivatives/liq-map-v3/hyperliquid/btcusdt/1w
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
- `scripts/precompute_hl_sidecar.py`
- `src/liquidationheatmap/hyperliquid/api_client.py`
- `.env.example`
- `docs/runbooks/hyperliquid-liqmap-checkpoint.md`

Supporting artifacts:

- `data/validation/hl_coinglass_360_audit.json`
- `data/validation/hl_coinglass_mass_redistribution_report.json`
- `data/validation/hl_coinglass_mass_redistribution_report.md`
- `tests/test_scripts/test_precompute_hl_sidecar.py`
- `tests/test_api_client.py`
- `tests/test_api/test_main.py`

## Important Caveat

The working tree is dirty beyond this track. Do not assume every modified file in
`git status` belongs to the Hyperliquid liq-map work.

Resume from this checkpoint by treating `v1` as preserved and `v2` as the safe
place for future experiments.
