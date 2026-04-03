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

### Precompute runtime alignment

On `2026-04-02`, the active host writer for `data/cache/hl_sidecar_v3_*.json`
was confirmed to be the user cron:

- `*/15 * * * * cd /media/sam/1TB/rektslug && .venv/bin/python scripts/precompute_hl_sidecar.py >> /tmp/hl_sidecar_cron.log 2>&1`

That command did **not** load repo runtime env, so every 15 minutes it rewrote
`v3` caches with selector defaults like:

- `objective: null`
- `selected_users: 250`
- `score_mode: notional`

even after the BTC/ETH selector experiments had produced better per-symbol
branches.

The fix is now:

1. `scripts/lib/runtime_env.sh` exports `HEATMAP_HYPERLIQUID_*` and
   `HEATMAP_HL_*` knobs loaded from `.env`
2. `scripts/run-precompute-hl-sidecar.sh` is the canonical runtime entrypoint
   for the cron writer
3. the wrapper applies stable `v3` defaults when env overrides are absent:
   - BTC: `objective=none`, `top_n=500`, `score_mode=notional`
   - ETH: `score_mode=concentration`, `top_n=300`,
     `share_power=1.0`, `positions_penalty=0.1`

Operational implication:

- future `v3` comparisons are only meaningful after confirming the active cron
  uses the wrapper entrypoint instead of calling Python directly

## 2026-04-02 CoinGlass Fresh-Capture Decoder Follow-up

Fresh CoinGlass Hyperliquid captures were created on `2026-04-02`:

- BTC: `data/validation/raw_provider_api/20260402T082851Z`
- ETH: `data/validation/raw_provider_api/20260402T082937Z`

These captures initially exposed a decoder regression in the local CoinGlass
toolchain, but the local decoder path has now been updated.

Observed facts:

- fresh response headers now carry versions like `v=55`, `v=66`, and `v=77`
- the existing local decoder still assumes the older seed-derivation path for
  non-`v=0` / non-`v=2` payloads
- the current live CoinGlass app bundle shows those newer versions use bundled
  constants, not the old URL-path-derived seed

Current consequence:

- fresh `2026-04-02` captures are now decodable again
- `v2` resolves the latest decodable local capture instead of falling back to
  `20260401T160752Z`
- the active local reference for BTC/ETH has moved forward to
  `data/validation/raw_provider_api/20260402T082937Z`

Runtime hardening already applied:

1. `v2` no longer blindly trusts the newest matching capture
2. the route now skips undecodable CoinGlass captures and falls back to the
   latest decodable local capture
3. `scripts/compare_hl_sidecar_vs_coinglass.py` now reports an undecodable
   capture cleanly instead of crashing on missing metrics fields

Applied decoder update:

1. `scripts/coinglass_decode_standalone.js` now derives seed sources for:
   - `v=55 -> 170b070da9654622`
   - `v=66 -> d6537d845a964081`
   - `v=77 -> 863f08689c97435b`
2. `scripts/compare_provider_liquidations.py` uses the same version-aware seed
   derivation
3. legacy captures without `v` still preserve the older `time` /
   `cache-ts-v2` fallback path

Immediate implication:

1. `v2` comparisons can again use the fresh `2026-04-02` captures
2. `v3` tuning should now be judged against those fresh captures, not the
   stale `2026-04-01` decode fallback

Fresh comparison snapshot against `20260402T082937Z`:

- BTC `v1`: `pearson_r=0.5182`, `KS=0.044`, `Wasserstein=7928.86`,
  `L/S diff=0.027`
- BTC `v3`: `pearson_r=0.405`, `KS=0.0802`, `Wasserstein=11065.36`,
  `L/S diff=0.1113`
- ETH `v1`: `pearson_r=0.8773`, `KS=0.0474`, `Wasserstein=369.2`,
  `L/S diff=0.066`
- ETH `v3`: `pearson_r=0.8711`, `KS=0.0348`, `Wasserstein=418.32`,
  `L/S diff=0.0066`

Interpretation:

- on the fresh reference, BTC `v1` currently beats BTC `v3`
- ETH `v3` improves balance and KS, but ETH `v1` still keeps a small edge on
  Pearson correlation and transport distance

Fresh BTC selector mini-sweep against the same `20260402T082937Z` reference:

- current BTC wrapper default (`balanced`, `top_n=350`):
  `pearson_r=0.2715`, `KS=0.0824`, `Wasserstein=11205.57`,
  `L/S diff=0.1223`
- `shape_first`, `top_n=350`:
  `pearson_r=0.331`, `KS=0.1612`, `Wasserstein=14056.3`,
  `L/S diff=0.2013`
- `notional`, `top_n=500`, no extra filters:
  `pearson_r=0.235`, `KS=0.0486`, `Wasserstein=8202.62`,
  `L/S diff=0.0291`
- `notional`, `top_n=400`, `min_target_share=0.4`, `max_position_count=3`:
  `pearson_r=0.3089`, `KS=0.1312`, `Wasserstein=13067.57`,
  `L/S diff=0.2036`

Current conclusion for BTC:

- no tested `v3` selector beats BTC `v1` on the fresh reference
- but the old BTC wrapper default (`balanced`, `350`) is no longer the best
  experimental baseline
- the least-wrong BTC `v3` branch right now is `notional`, `top_n=500`,
  because it keeps `KS`, `Wasserstein`, and `L/S diff` close to BTC `v1`
  even though Pearson correlation remains lower

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
- `HEATMAP_HL_TOP_POSITION_SCORE_MODE`
- `HEATMAP_HL_TOP_POSITION_CANDIDATE_POOL_TOP_N`
- `HEATMAP_HL_TOP_POSITION_DISTANCE_FLOOR_BPS`
- `HEATMAP_HL_TOP_POSITION_REQUIRE_SIDE_CONSISTENCY`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY`
- `HEATMAP_HL_TOP_POSITION_OBJECTIVE`
- `HEATMAP_HL_TOP_POSITION_MIN_TARGET_SHARE`
- `HEATMAP_HL_TOP_POSITION_MAX_POSITION_COUNT`
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

## 2026-04-01 V3 Follow-up Experiments

Two more `v3` experiments were completed after the initial checkpoint.

### 1. `liq_intensity` score mode is not the right next lever

An experimental `v3` score mode was added to rank selected users by:

- target notional
- adjusted by distance from current mark price to estimated liquidation price

This was tested with:

- `HEATMAP_HL_TOP_POSITION_SCORE_MODE=liq_intensity`
- `HEATMAP_HL_TOP_POSITION_REQUIRE_SIDE_CONSISTENCY=true`

Observed result against the fresh local `v2` replay:

- BTC combined `pearson_r`: `0.018`
- ETH combined `pearson_r`: `0.2443`

Interpretation:

- the selection becomes cleaner (`sign_mismatch=0`)
- but the aggregate bucket shape gets worse
- so `near-liq weighting` on the current sidecar universe is **not** the main
  missing ingredient

Treat this branch as a useful diagnostic knob, not the preferred `v3` default.

### 1b. Two-pass `live_liq_intensity` with a larger candidate pool is only a mixed improvement

`v3` now also supports a two-pass path:

1. select a wider candidate pool by raw target notional
2. fetch live overrides for that pool
3. rerank by liquidation intensity using the live liquidation prices

Relevant knob:

- `HEATMAP_HL_TOP_POSITION_CANDIDATE_POOL_TOP_N`

Experiment run on `2026-04-01`:

- `HEATMAP_HL_TOP_POSITION_SCORE_MODE=live_liq_intensity`
- `HEATMAP_HL_TOP_POSITION_CANDIDATE_POOL_TOP_N=400`
- `HEATMAP_HL_TOP_POSITION_REQUIRE_SIDE_CONSISTENCY=false`

Observed result vs the baseline selected-user-enriched `v3`:

- BTC `pearson_r`: `0.0532 -> 0.0739`
- BTC `KS`: `0.0626 -> 0.1032`
- BTC `Wasserstein`: `9925.37 -> 12940.18`
- BTC `L/S ratio diff`: `0.0024 -> 0.0593`

- ETH `pearson_r`: `0.232 -> 0.2348`
- ETH `KS`: `0.1396 -> 0.1398`
- ETH `Wasserstein`: `468.65 -> 498.97`
- ETH `L/S ratio diff`: `0.0832 -> 0.0633`

Interpretation:

- BTC gains a little on Pearson correlation
- but transport distance and balance metrics worsen
- ETH is basically flat
- the two-pass path is promising enough to keep in code, but not strong enough
  yet to replace the current baseline

For that reason, the local `v3` cache was restored to the selected-user-enriched
baseline after the experiment.

### 2. Extending live enrichment to the selected `v3` universe helps scale, not shape

`v3` now extends live enrichment beyond the shared top-`N` subset so it can
request live overrides for users selected into the `v3` universe itself.

Observed coverage after this change with the baseline
`selection_strategy=global` and `score_mode=notional`:

- BTC: `220` live overrides across `222` included users
- ETH: `214` live overrides across `216` included users

Direct before/after compare with the same `20260401T160752Z` CoinGlass capture:

- BTC `pearson_r`: `0.0583 -> 0.0532`
- BTC `KS`: `0.0702 -> 0.0626`
- BTC `Wasserstein`: `10508.47 -> 9925.37`
- BTC `L/S ratio diff`: `0.0131 -> 0.0024`

- ETH `pearson_r`: `0.2353 -> 0.232`
- ETH `KS`: `0.1438 -> 0.1396`
- ETH `Wasserstein`: `474.83 -> 468.65`
- ETH `L/S ratio diff`: `0.0879 -> 0.0832`

Interpretation:

- better live liquidation prices materially improve:
  - scale alignment
  - long/short balance
  - transport-style distance metrics
- but they do **not** materially improve Pearson shape correlation

This is an important deduction:

- the remaining blocker is now primarily the **selected user universe**
- not the liquidation-price solver for the users already included

### 3. Duplicate CoinGlass rows are not the main issue

Fresh local CoinGlass capture counts:

- BTC: `278` rows, `275` unique `userId`
- ETH: `154` rows, `154` unique `userId`

So the current mismatch is not mainly explained by many duplicated
CoinGlass rows per user.

### 4. Sidecar top-notional accounts are often more complex than a naive top-position view

Probe on the real sidecar state (`top 250` by raw target notional):

- BTC:
  - median positions: `2`
  - mean positions: `8.77`
  - median target share: `0.948`
  - mean target share: `0.7439`
  - single-position accounts: `118`
  - accounts with `<=3` positions: `176`

- ETH:
  - median positions: `2`
  - mean positions: `11.41`
  - median target share: `0.6151`
  - mean target share: `0.6193`
  - single-position accounts: `78`
  - accounts with `<=3` positions: `157`

Interpretation:

- BTC top-notional users are mixed: many are focused, but the tail contains
  very complex books
- ETH top-notional users are materially noisier on average
- this supports an explicit concentration-aware selector in `v3`

### 5. `concentration` selector is promising, but not yet a universal default

`v3` now supports a `concentration` score mode:

- high target notional still matters
- target share is rewarded
- books with many positions are penalized

Score form:

- `target_notional * target_share^share_power / position_penalty`

Relevant knobs:

- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY`

The selector now also supports per-symbol overrides by suffixing the symbol:

- `..._BTC`
- `..._ETH`

Examples:

- `HEATMAP_HL_TOP_POSITION_SCORE_MODE_BTC=concentration`
- `HEATMAP_HL_TOP_POSITION_SCORE_MODE_ETH=notional`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER_BTC=1.0`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY_ETH=0.1`

Two experiments were run on `2026-04-02`.

#### Aggressive concentration

Settings:

- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER=2.0`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY=0.2`

Result vs the selected-user-enriched baseline:

- BTC:
  - `pearson_r`: `0.0532 -> 0.1241`
  - `KS`: `0.0626 -> 0.0716`
  - `Wasserstein`: `9925.37 -> 12994.17`
  - `L/S diff`: `0.0024 -> 0.1236`

- ETH:
  - `pearson_r`: `0.232 -> 0.2427`
  - `KS`: `0.1396 -> 0.149`
  - `Wasserstein`: `468.65 -> 521.82`
  - `L/S diff`: `0.0832 -> 0.0002`

Interpretation:

- BTC shape correlation improves a lot, but balance gets too distorted
- ETH gets nearly perfect L/S balance, but transport distance worsens

#### Lighter concentration

Settings:

- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER=1.0`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY=0.1`

Result vs the selected-user-enriched baseline:

- BTC:
  - `pearson_r`: `0.0532 -> 0.0911`
  - `KS`: `0.0626 -> 0.09`
  - `Wasserstein`: `9925.37 -> 11628.16`
  - `L/S diff`: `0.0024 -> 0.0436`

- ETH:
  - `pearson_r`: `0.232 -> 0.2382`
  - `KS`: `0.1396 -> 0.1356`
  - `Wasserstein`: `468.65 -> 479.88`
  - `L/S diff`: `0.0832 -> 0.0133`

Interpretation:

- the lighter version is more balanced than the aggressive one
- ETH is plausibly improved overall
- BTC still trades better shape correlation for worse balance/transport metrics

Conclusion:

- `concentration` is worth keeping in code
- but it is not yet strong enough as a single global default for both BTC and
  ETH
- the code now supports symbol-specific selector policy
- the next step is to choose actual BTC/ETH runtime settings, not add more
  blind global-weight tuning

### 6. First practical symbol-specific policy: `BTC=notional`, `ETH=concentration-lite`

A mixed runtime policy was tested on `2026-04-02`:

- `HEATMAP_HL_TOP_POSITION_SCORE_MODE_BTC=notional`
- `HEATMAP_HL_TOP_POSITION_SCORE_MODE_ETH=concentration`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER_ETH=1.0`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY_ETH=0.1`

Compared against the baseline cache captured immediately before this test:

- BTC:
  - `pearson_r`: `-0.0103 -> -0.0106`
  - `KS`: `0.0732 -> 0.074`
  - `Wasserstein`: `10032.13 -> 9971.65`
  - `L/S diff`: `0.0232 -> 0.007`

- ETH:
  - `pearson_r`: `0.240 -> 0.2451`
  - `KS`: `0.1418 -> 0.1356`
  - `Wasserstein`: `459.38 -> 475.19`
  - `L/S diff`: `0.0688 -> 0.0109`

Interpretation:

- BTC is effectively unchanged, with slightly better balance
- ETH improves materially on balance and modestly on shape correlation
- ETH loses some transport-distance quality, but the overall trade-off is
  better than the pure global `notional` selector

This makes the mixed policy the current best practical experimental setting for
`v3`, even though it is still not a final production default.

### 7. Budget sweep: `top_n` is now a real per-symbol lever

On `2026-04-02` I ran a focused `top_n` sweep against the fresh replay capture
`data/validation/raw_provider_api/20260401T160752Z`, using the current mixed
selector baseline:

- BTC: `score_mode=notional`
- ETH: `score_mode=concentration`
- ETH concentration weights: `share_power=1.0`,
  `positions_penalty=0.1`
- Hyperliquid Info forced through mirror-first fallback:
  `http://localhost:3001/info,http://10.0.0.1:3001/info,https://api.hyperliquid.xyz/info`

BTC sweep (`notional`):

- `top_n=150`: `pearson_r=-0.0278`, `KS=0.0958`, `Wasserstein=10946.7`,
  `L/S diff=0.0547`
- `top_n=200`: `pearson_r=-0.0192`, `KS=0.0822`, `Wasserstein=10298.21`,
  `L/S diff=0.0237`
- `top_n=250`: `pearson_r=-0.0106`, `KS=0.074`, `Wasserstein=9971.65`,
  `L/S diff=0.007`
- `top_n=300`: `pearson_r=0.0011`, `KS=0.072`, `Wasserstein=9794.13`,
  `L/S diff=0.0011`
- `top_n=350`: `pearson_r=0.0148`, `KS=0.0732`, `Wasserstein=9708.03`,
  `L/S diff=0.006`

ETH sweep (`concentration-lite`):

- `top_n=150`: `pearson_r=0.2285`, `KS=0.138`, `Wasserstein=490.19`,
  `L/S diff=0.0028`
- `top_n=200`: `pearson_r=0.2382`, `KS=0.1378`, `Wasserstein=485.07`,
  `L/S diff=0.0046`
- `top_n=250`: `pearson_r=0.2451`, `KS=0.1356`, `Wasserstein=475.19`,
  `L/S diff=0.0109`
- `top_n=300`: `pearson_r=0.2501`, `KS=0.138`, `Wasserstein=472.44`,
  `L/S diff=0.0235`
- `top_n=350`: `pearson_r=0.2536`, `KS=0.1402`, `Wasserstein=470.77`,
  `L/S diff=0.0269`

Interpretation:

- `top_n` is no longer noise; it materially changes `v3`
- BTC benefits from a larger budget more clearly than ETH
- BTC improves almost monotonically through `350`, but the improvement is still
  mostly on scale/transport and only weakly on shape correlation
- ETH improves more gently; beyond `250` the correlation keeps rising, but the
  long/short balance starts drifting
- this means the next practical runtime policy should be per-symbol on both
  selector mode and target budget

Current practical experimental budget policy to try on the live `v3` route:

- `HEATMAP_HL_TOP_POSITION_SCORE_MODE_BTC=notional`
- `HEATMAP_HL_TOP_POSITION_TOP_N_BTC=350`
- `HEATMAP_HL_TOP_POSITION_SCORE_MODE_ETH=concentration`
- `HEATMAP_HL_TOP_POSITION_TOP_N_ETH=300`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_SHARE_POWER_ETH=1.0`
- `HEATMAP_HL_TOP_POSITION_CONCENTRATION_POSITIONS_PENALTY_ETH=0.1`

Rationale:

- BTC needs the larger budget more than it needs extra selector complexity
- ETH already benefits from `concentration-lite`, and `300` is the best
  compromise tested between shape gain and balance drift
- these are still experimental runtime settings, not hardcoded defaults

### 8. BTC-only selector filters finally produce real shape lift

After the budget sweep, BTC still had the same structural issue:

- larger `top_n` helped
- but `long_pearson_r` remained negative
- and the selector was still taking many broad multi-book accounts

So I tested two explicit universe filters above the current BTC `notional`
ranking:

- `min_target_share`
- `max_position_count`

These are now implemented as per-symbol selector knobs:

- `HEATMAP_HL_TOP_POSITION_MIN_TARGET_SHARE`
- `HEATMAP_HL_TOP_POSITION_MAX_POSITION_COUNT`
- and symbol-specific overrides like `..._BTC`

Focused BTC experiments on the same `20260401T160752Z` capture:

- baseline `top_n=350`:
  - `pearson_r=0.0155`
  - `KS=0.0728`
  - `Wasserstein=9697.69`
  - `L/S diff=0.0043`
  - `long_pearson_r=-0.0584`
  - `short_pearson_r=0.0812`

- `max_position_count=3`:
  - `pearson_r=0.0719`
  - `KS=0.0656`
  - `Wasserstein=11847.75`
  - `L/S diff=0.0779`
  - `long_pearson_r=-0.0023`
  - `short_pearson_r=0.1364`

- `min_target_share=0.7`:
  - `pearson_r=0.114`
  - `KS=0.136`
  - `Wasserstein=17310.79`
  - `L/S diff=0.1383`
  - `long_pearson_r=0.047`
  - `short_pearson_r=0.162`

- `max_position_count=3` + `min_target_share=0.7`:
  - `pearson_r=0.1468`
  - `KS=0.132`
  - `Wasserstein=16759.84`
  - `L/S diff=0.0565`
  - `long_pearson_r=0.0488`
  - `short_pearson_r=0.2256`

Interpretation:

- this is the first BTC-only lever that clearly improves shape correlation
- it also fixes the worst sign on the long-side Pearson
- but it does so by paying a meaningful transport/balance cost
- so the filter pair is worth keeping as an explicit experimental branch, not
  yet as the unquestioned default BTC runtime policy

Current practical BTC experiment to visualize next:

- `HEATMAP_HL_TOP_POSITION_SCORE_MODE_BTC=notional`
- `HEATMAP_HL_TOP_POSITION_TOP_N_BTC=350`
- `HEATMAP_HL_TOP_POSITION_MIN_TARGET_SHARE_BTC=0.7`
- `HEATMAP_HL_TOP_POSITION_MAX_POSITION_COUNT_BTC=3`

Current conclusion:

- BTC is now clearly bottlenecked by selector tradeoffs, not missing plumbing
- the decision is no longer “can we move the shape?”
- it is “which metric tradeoff do we want the experimental `v3` to prefer?”

### 9. BTC frontier: there is a real `balanced` branch and a real `shape-first` branch

I ran a softer BTC frontier sweep around the hard `0.7 / 3` filter.

Representative points against the same fresh capture:

- baseline `350`, no extra filters:
  - `pearson_r=0.0166`
  - `KS=0.0716`
  - `Wasserstein=9643.87`
  - `L/S diff=0.01`
  - `long_pearson_r=-0.057`

- `max_position_count=3` only:
  - `pearson_r=0.0721`
  - `KS=0.0654`
  - `Wasserstein=11822.96`
  - `L/S diff=0.0666`
  - `long_pearson_r=-0.0011`

- `max_position_count=3` + `min_target_share=0.6`:
  - `pearson_r=0.1384`
  - `KS=0.1326`
  - `Wasserstein=16450.15`
  - `L/S diff=0.0889`
  - `long_pearson_r=0.0494`

- `max_position_count=3` + `min_target_share=0.65`:
  - `pearson_r=0.1405`
  - `KS=0.1328`
  - `Wasserstein=16539.93`
  - `L/S diff=0.0758`
  - `long_pearson_r=0.0499`

Interpretation:

- there is no free lunch on BTC
- but there are now two defensible branches:
  - `balanced`: keep transport/balance degradation limited and lift shape a bit
  - `shape_first`: explicitly accept worse transport/balance in exchange for a
    strong shape lift

The cleanest practical presets are:

- `balanced`
  - `score_mode=notional`
  - `max_position_count=3`
  - no extra `target_share` floor

- `shape_first`
  - `score_mode=notional`
  - `max_position_count=3`
  - `min_target_share=0.6`

These presets are now codified through:

- `HEATMAP_HL_TOP_POSITION_OBJECTIVE=default|balanced|shape_first`
- plus the existing explicit knobs which still override the preset when set

Current recommendation:

- use `balanced` for the default BTC experimental branch
- keep `shape_first` as the deliberate comparison branch when visually
  validating against CoinGlass

### 10. 2026-04-02 runtime closure: the active writer now matches the intended `v3` branch

The runtime loop was closed on `2026-04-02`.

What was wrong:

- the active host cron rewrote `data/cache/hl_sidecar_v3_*.json` every `15`
  minutes by calling Python directly
- that path did not load the Hyperliquid selector env
- so the active caches silently fell back to the generic runtime defaults

Confirmed active writer now:

- `*/15 * * * * cd /media/sam/1TB/rektslug && ./scripts/run-precompute-hl-sidecar.sh >> /tmp/hl_sidecar_cron.log 2>&1`

Confirmed active `v3` cache state after the wrapper rerun:

- BTC:
  - `objective=balanced`
  - `score_mode=notional`
  - `selected_users=350`
  - `included_users=332`
  - `live_override_users=327`
- ETH:
  - `score_mode=concentration`
  - `selected_users=300`
  - `included_users=289`
  - `live_override_users=288`

Measured against the fresh CoinGlass capture `20260401T160752Z`:

- BTC `v1`:
  - `pearson_r=-0.0085`
  - `KS=0.0626`
  - `Wasserstein=9829.55`
  - `L/S diff=0.0085`
- BTC `v3 balanced`:
  - `pearson_r=-0.137`
  - `KS=0.0758`
  - `Wasserstein=12981.63`
  - `L/S diff=0.131`

- ETH `v1`:
  - `pearson_r=0.2905`
  - `KS=0.1336`
  - `Wasserstein=486.85`
  - `L/S diff=0.049`
- ETH `v3 current`:
  - `pearson_r=0.2493`
  - `KS=0.1288`
  - `Wasserstein=502.1`
  - `L/S diff=0.0216`

Interpretation:

- the runtime plumbing issue is resolved
- the current active `v3` branch is now the intended one
- but the model gap remains:
  - BTC `v3 balanced` is still worse than `v1`
  - ETH `v3` improves long/short balance, but does not beat `v1` on shape
    or transport

This is the cleanest current conclusion:

- stop treating runtime drift as the blocker
- resume from selector-model work again
- BTC especially still needs a better universe projector, not more plumbing

## 2026-04-02 Runtime Verification Follow-up

I reran the canonical wrapper on `2026-04-02` and confirmed the bootstrap path
is healthy on the Hyperliquid mirrors:

- `meta` succeeds on `http://localhost:3001/info`
- `allBorrowLendReserveStates` succeeds on `http://localhost:3001/info`
- the same two payloads also succeed on `http://10.0.0.1:3001/info`

The actual issue was not mirror support. The live precompute simply takes long
enough that earlier manual checks stopped too early.

Observed wrapper run:

- BTC `v1` written successfully
- BTC `v3` written successfully after a wider selected-user enrichment pass:
  - `targeted=393`
  - `applied=334`
  - `failed=59`
- ETH `v1` written successfully
- ETH `v3` written successfully:
  - `targeted=192`
  - `applied=180`
  - `failed=12`

Fresh measured distances against CoinGlass capture
`data/validation/raw_provider_api/20260402T082937Z` after the rerun:

- BTC `v1`:
  - `pearson_r=0.3293`
  - `KS=0.043`
  - `Wasserstein=8052.42`
  - `L/S diff=0.023`
- BTC `v3`:
  - `pearson_r=0.2294`
  - `KS=0.0486`
  - `Wasserstein=8167.14`
  - `L/S diff=0.027`

- ETH `v1`:
  - `pearson_r=0.3583`
  - `KS=0.1578`
  - `Wasserstein=373.54`
  - `L/S diff=0.0666`
- ETH `v3`:
  - `pearson_r=0.3196`
  - `KS=0.153`
  - `Wasserstein=422.0`
  - `L/S diff=0.0059`

Interpretation:

- the runtime loop is now confirmed end-to-end
- BTC `v1` still clearly beats BTC `v3`
- ETH `v3` still wins on long/short balance, but not on overall shape or
  transport
- the current `v3` selector family is still not the path to a BTC improvement

## 2026-04-02 `band_synthesis` falsifier

To test the Gemini hypothesis cheaply before adding a user-level
`risk_clusters` selector, I added a probe mode:

- `HEATMAP_HL_TOP_POSITION_SCORE_MODE_BTC=band_synthesis`

This mode does **not** select users. It starts from the already-built `v1`
bucket map and keeps only the heaviest liquidation buckets.

This is intentionally a falsifier:

- if BTC improves materially, then a cluster-first projector is worth building
- if BTC does not improve, then `risk_clusters` is much less likely to be the
  missing core abstraction

Measured against fresh CoinGlass capture
`data/validation/raw_provider_api/20260402T082937Z` using the active BTC `v1`
cache as the seed:

- global `top_buckets=250`:
  - `pearson_r=0.1218`
  - `KS=0.043`
  - `Wasserstein=8680.32`
  - `L/S diff=0.0118`
- global `top_buckets=500`:
  - `pearson_r=0.1800`
  - `KS=0.0424`
  - `Wasserstein=8348.52`
  - `L/S diff=0.0117`
- global `top_buckets=1000`:
  - `pearson_r=0.2226`
  - `KS=0.0436`
  - `Wasserstein=8024.96`
  - `L/S diff=0.0192`

Reference points:

- BTC `v1`: `pearson_r=0.3293`, `KS=0.043`, `Wasserstein=8052.42`,
  `L/S diff=0.023`
- BTC current `v3`: `pearson_r=0.2294`, `KS=0.0486`, `Wasserstein=8167.14`,
  `L/S diff=0.027`

Conclusion:

- the cheap cluster falsifier did **not** beat `v1`
- it also did not materially beat the current BTC `v3`
- so the simple thesis `CoinGlass ~= heaviest full-map clusters` is now weaker
- if a future `risk_clusters` selector is attempted, it should be treated as a
  narrower follow-up experiment, not as the new default direction

### Symbol-scoped rerun fix

During the verification I confirmed a separate bug:

- `scripts/run-precompute-hl-sidecar.sh` loaded `HEATMAP_SYMBOLS_SHELL`
- but `scripts/precompute_hl_sidecar.py` ignored it and always ran both `BTC`
  and `ETH`

That is now fixed. The Python precompute resolves symbols from:

- `HEATMAP_SYMBOLS_SHELL`
- or `HEATMAP_SYMBOLS`

Supported examples:

```bash
HEATMAP_SYMBOLS_SHELL=BTCUSDT ./scripts/run-precompute-hl-sidecar.sh
HEATMAP_SYMBOLS=BTC,ETH uv run python scripts/precompute_hl_sidecar.py
```

## Current Decision For The Next Session

As of `2026-04-02`, it is **not** worth continuing to tune the current
user-first `v3` line (`top users -> live enrich -> rebucket`) with more small
selector tweaks.

Why:

- BTC `v1` still beats BTC `v3` on the fresh reference
- the cheap `band_synthesis` falsifier did not validate the simple
  `CoinGlass ~= heaviest full-map clusters` thesis
- live enrichment and selector-weight tuning have already shown diminishing
  returns

So the current recommendation is:

1. freeze the current `v3` branch as an experimental baseline
2. keep `v1` as the truthful/internal production baseline
3. do **not** spend another session on more user-first selector tuning
4. if work continues, start a conceptually different branch:
   - `v3b` / `position-first`
   - `risk-first`
   - or another non-user-first projector

## Recommended Next Experiment

If a new session continues this track, the next experiment should be treated as
a fresh hypothesis test, not an extension of the current selector family.

Recommended direction:

1. build a `position-first` or `risk-first` projector prototype
2. compare it against the same fresh `v2` replay capture
3. use a hard kill criterion on BTC:
   - it should beat `v1` on at least `2/3` of:
     - `pearson_r`
     - `KS`
     - `Wasserstein`
4. if it does not, stop pursuing CoinGlass-style imitation as a primary track

What should **not** be the default next direction:

- more tuning of `min_target_share`
- more tuning of `max_position_count`
- more tuning of `concentration` weights
- promoting `risk_clusters` or `band_synthesis` to runtime defaults

## 2026-04-02 `risk-first` Prototype Verdict

A first account-level `risk-first` projector prototype was implemented as `v5`
(`internal-risk-first` / `hl_sidecar_v5_*`), using:

- a target-position candidate pool by raw target notional
- live Hyperliquid account state over that pool
- account-level fragility signals
  - cross: `crossMaintenanceMarginUsed / accountValue`
  - PM / unified: `portfolio_margin_ratio`
- liquidation-distance weighting
- extra stress terms from off-target notional and borrowed notional

Runtime used for the first real BTC experiment:

```bash
HEATMAP_HL_RISK_FIRST_TOP_N_BTC=500 \
HEATMAP_HL_RISK_FIRST_CANDIDATE_POOL_TOP_N_BTC=1000 \
./scripts/run-precompute-hl-sidecar.sh
```

Fresh comparison capture:

- `data/validation/raw_provider_api/20260402T082937Z`

Saved comparison outputs:

- `data/validation/comparison_hl_btc_cache_v1_20260402T082937Z.json`
- `data/validation/comparison_hl_btc_cache_v5_risk_first_20260402T082937Z.json`

BTC result against the same fresh reference:

- BTC `v1`:
  - `pearson_r=0.1634`
  - `KS=0.0486`
  - `Wasserstein=8491.24`
- BTC `v5 risk-first`:
  - `pearson_r=0.0626`
  - `KS=0.0608`
  - `Wasserstein=10007.13`

Decision:

- BTC `v5 risk-first` does **not** beat BTC `v1` on any of the required `3`
  metrics
- therefore the stop criterion is triggered for this track
- do **not** continue CoinGlass-shape imitation as the primary Hyperliquid
  direction after this experiment
- keep `v5` as a documented experimental branch, not a promoted default

## Commands To Resume

Start the local server:

```bash
uv run uvicorn src.liquidationheatmap.api.main:app --host 0.0.0.0 --port 8016
```

Regenerate the active Hyperliquid sidecar caches with the canonical runtime
entrypoint:

```bash
./scripts/run-precompute-hl-sidecar.sh
```

Regenerate only BTC:

```bash
HEATMAP_SYMBOLS_SHELL=BTCUSDT ./scripts/run-precompute-hl-sidecar.sh
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
http://10.0.0.2:8016/chart/derivatives/liq-map-v4/hyperliquid/ethusdt/1w
http://10.0.0.2:8016/chart/derivatives/liq-map-v4/hyperliquid/btcusdt/1w
http://10.0.0.2:8016/chart/derivatives/liq-map-v5/hyperliquid/ethusdt/1w
http://10.0.0.2:8016/chart/derivatives/liq-map-v5/hyperliquid/btcusdt/1w
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
- `scripts/run-precompute-hl-sidecar.sh`
- `scripts/lib/runtime_env.sh`
- `src/liquidationheatmap/hyperliquid/api_client.py`
- `.env.example`
- `docs/runbooks/hyperliquid-liqmap-checkpoint.md`

Supporting artifacts:

- `data/validation/hl_coinglass_360_audit.json`
- `data/validation/hl_coinglass_mass_redistribution_report.json`
- `data/validation/hl_coinglass_mass_redistribution_report.md`
- `tests/test_scripts/test_precompute_hl_sidecar.py`
- `tests/unit/test_runtime_compose.py`
- `tests/test_api_client.py`
- `tests/test_api/test_main.py`

## Important Caveat

The working tree is dirty beyond this track. Do not assume every modified file in
`git status` belongs to the Hyperliquid liq-map work.

Resume from this checkpoint by treating `v1` as preserved and `v2` as the safe
place for future experiments.

## 2026-04-02 Late Handoff For A Clean Next Session

This section supersedes the informal tail of the current chat and should be the
starting point for the next clean session.

### State Of The Track

- `v1` remains the truthful/internal Hyperliquid baseline.
- `v2` remains the local CoinGlass top-position replay baseline.
- `v3` remains frozen as the user-first experimental baseline; do not tune it
  further.
- `v4` (`position-first`) is kept only as a documented exploratory branch.
- `v5` (`risk-first`) is the first conceptually different branch that was
  actually tested; it failed the global BTC stop criterion against `v1`.

So:

- do **not** resume CoinGlass-shape imitation as the primary Hyperliquid track
- do **not** spend time on more selector-family tweaks
- keep the experimental branches for analysis, not promotion

### Important Clarification About `v2`

An important UI/contract mismatch was found and fixed after the first `v5`
verdict:

- the shared Hyperliquid renderer was forcing `coin` display mode for all
  Hyperliquid variants, including `v2`
- `v2` was also inheriting the display `grid` frame from the `v1` cache instead
  of deriving it from the decoded CoinGlass top-position payload

Fixes shipped:

- `v2` now exposes `display_unit="usd"` from the backend
- the shared frontend now honors `display_unit` when present
- the `v2` grid is now computed from the decoded CoinGlass buckets instead of
  reusing the `v1` frame

Implication:

- prior **visual** comparisons of `v2` vs CoinGlass were not trustworthy on
  axis/unit fidelity
- the **data** comparisons and saved BTC verdicts remain valid, because they
  already operated on raw bucket `volume` in nominal `USD`, not on frontend
  `coin` conversions

### What To Do Next

The next clean session should **not** continue from visuals.

The next task is:

1. build a clean `raw-USD` comparison report for BTC using:
   - `v1`
   - `v2`
   - `v5`
2. compare only data payloads:
   - `long_buckets`
   - `short_buckets`
   - `volume`
3. report both:
   - full-range metrics
   - local windows around the mark: `±3%`, `±5%`, `±10%`, `±15%`, `±20%`
4. treat `v3` and `v4` only as appendix/control variants, not as decision
   candidates

The question for the next session is no longer:

- "which UI looks more like CoinGlass?"

It is:

- "does the `raw-USD` bucket distribution of `v5` add useful local alignment
  versus `v1`, despite the failed global stop criterion?"

### External Incident: `hyperliquid-node` Vendor Dataset Contract

The upstream incident report to keep in scope lives outside this repo:

- `/media/sam/1TB/hyperliquid-node/docs/INCIDENT-REPORT-2026-04-02-VENDOR-DATASET-MARCH-2026.md`

Producer-side references mentioned there:

- `/media/sam/1TB/hyperliquid-node/README.md`
- `/media/sam/1TB/hyperliquid-node/ARCHITECTURE.md`
- `/media/sam/1TB/hyperliquid-node/docs/RUNBOOK.md`
- `/media/sam/1TB/hyperliquid-node/scripts/audit_vendor_dataset.py`

Current impact assessment for Rektslug:

- low direct impact on the current Hyperliquid liq-map branches (`v1`/`v3`/`v4`/`v5`)
- high potential impact on future replay-exact or order-aware work

Reason:

- current liq-map branches are still primarily `ABCI anchor + live /info`
  driven
- they are **not** primarily using the March 2026 filtered historical
  `order_statuses` / `raw_book_diffs` contract that was called out in the
  incident
- but future work on resting-order / reserved-margin / historical replay will
  depend on that producer contract much more heavily

What Rektslug should assume going forward:

- do not treat the filtered hot root alone as a historical contract
- require explicit producer health / audit signals before depending on those
  datasets
- keep consumer-owned retention/checkpointing for anything beyond the rolling
  producer window

### Transferability To Binance / Bybit

The knowledge from this Hyperliquid investigation is transferable mostly as
method, not as a direct projector transplant.

Reusable:

- compare payloads in raw `USD`, not by UI appearance
- separate near-price/core behavior from tails
- use explicit stop criteria
- distinguish `display artifact` from `data artifact`

Not directly reusable:

- Hyperliquid `risk-first` depends on account-level state and PM/cross account
  fragility
- equivalent public account-level observables do not exist in the same way for
  Binance / Bybit

Current practical reading:

- Binance can reuse the evaluation method and should be approached as a
  `public-flow-first` problem
- Bybit cannot yet reuse much operationally until a reliable public/historical
  liquidation source is in place

### Resume Checklist

For the next clean session, do only this:

```bash
sed -n '1196,9999p' docs/runbooks/hyperliquid-liqmap-checkpoint.md
uv run uvicorn src.liquidationheatmap.api.main:app --host 0.0.0.0 --port 8016
```

Then immediately work on:

- a `raw-USD` BTC comparison report for `v1` vs `v2` vs `v5`

Useful URLs once the server is up:

```bash
http://10.0.0.2:8016/chart/derivatives/liq-map/hyperliquid/btcusdt/1w
http://10.0.0.2:8016/chart/derivatives/liq-map-v2/hyperliquid/btcusdt/1w
http://10.0.0.2:8016/chart/derivatives/liq-map-v5/hyperliquid/btcusdt/1w
```

But again: those URLs are for sanity checks only. The next decision should be
made from payload-level `USD` comparisons, not from the browser rendering.

## 2026-04-03 BTC `raw-USD` Variant Report Result

The BTC `raw-USD` comparison report requested in the late handoff is now
materialized at:

- `data/validation/comparison_hl_btc_variants_raw_usd.json`

Important implementation note:

- the report builder was corrected to use the real `v2` replay path
  (`coinglass-top-position-local` from the latest decodable local capture)
  rather than the unrelated `v4` cache

Resolved `v2` source for this run:

- `data/validation/raw_provider_api/20260402T082937Z`

Global result summary:

- `v1` vs `v2`:
  - `pearson_r=0.179`
  - `KS=0.0674`
  - `Wasserstein=8705.52`
- `v1` vs `v5`:
  - `pearson_r=0.379`
  - `KS=0.0678`
  - `Wasserstein=3474.83`
- `v2` vs `v5`:
  - `pearson_r=-0.1629`
  - `KS=0.1096`
  - `Wasserstein=11703.72`

Near-mark local-window result summary:

- `v1` vs `v5` remains strongly aligned in every tested local window:
  - `±3%: pearson_r=0.9388`
  - `±5%: pearson_r=0.9213`
  - `±10%: pearson_r=0.9127`
  - `±15%: pearson_r=0.8753`
  - `±20%: pearson_r=0.8766`
- `v1` vs `v2` stays near zero or slightly negative in the same windows:
  - `±3%: pearson_r=-0.0298`
  - `±5%: pearson_r=-0.0226`
  - `±10%: pearson_r=-0.0155`
  - `±15%: pearson_r=-0.0153`
  - `±20%: pearson_r=-0.009`
- `v2` vs `v5` also stays negative in the same windows:
  - `±3%: pearson_r=-0.3827`
  - `±5%: pearson_r=-0.1775`
  - `±10%: pearson_r=-0.1308`
  - `±15%: pearson_r=-0.1638`
  - `±20%: pearson_r=-0.1602`

Interpretation:

- `v5` is materially closer to `v1` than to the `v2` CoinGlass replay
- the new local-window report does **not** show `v5` collapsing the near-mark
  raw-`USD` gap toward `v2`
- so the answer to the handoff question is currently:
  - no, `v5` does not show useful local alignment toward `v2` that would justify
    resuming it as the primary Hyperliquid direction

Decision after this report:

- keep `v1` as the truthful/internal Hyperliquid baseline
- keep `v2` as the replay/control baseline
- keep `v5` as a documented experimental branch only
- do **not** reopen `risk-first` tuning as the main next task on the strength
  of this report alone

If future work continues, it should be limited to:

- documenting this result cleanly
- using `v3`/`v4` only as appendix/control references if needed
- moving attention to other exchange tracks or to a different Hyperliquid
  method, not more selector-family tuning

## Ensemble / Ex-Post Voting Note

It does make conceptual sense to ask whether these branches could later be
combined, but only under a stricter framing than "blend the heatmaps".

Important distinction:

- `v1` is the current internal/truthful full-universe map
- `v2` is a replay/control built from local CoinGlass top-position payloads
- `v5` is an internal experimental projector

So a naive ensemble of `v1` + `v2` + `v5` would mix:

- different universes
- different product meanings
- different dependency contracts

For that reason, do **not** define a blended ensemble as the new canonical
Hyperliquid map by default.

What would make sense instead is a separate predictive layer:

- keep `v1` as the canonical/internal map
- treat `v2`/`v5`/future variants as candidate signals
- evaluate them against **future realized liquidation outcomes**
- only then learn a weighted combination for prediction/alerting

In other words:

- ensemble as a research/prediction overlay: yes, potentially sensible
- ensemble as the default semantic replacement for `v1`: not justified now

### Why Hard Voting Is The Wrong Shape

These variants output bucketed distributions, not simple labels.

So "voting" should not mean:

- majority vote by branch

It should mean something closer to:

- weighted combination of normalized bucket mass
- or weighted ranking of near-price buckets
- or a meta-model that consumes per-variant features and outputs predicted
  future liquidation density

### What Would Be Required

To make an ensemble defensible, first build an ex-post evaluation dataset:

- timestamped model outputs for `v1` / `v5` / future candidates
- subsequent realized liquidation observations over a fixed horizon
  (`15m`, `1h`, `4h`, etc.)
- a stable bucket alignment so predictions and outcomes share the same grid

Then score each branch on forward outcomes, for example with:

- top-band hit rate near realized liquidation clusters
- recall / precision for top-`k` predicted bands
- Wasserstein or other transport distance to realized event distribution
- calibration of predicted mass vs realized event concentration

### Recommended Future Rule

If this line is ever resumed, use this rule:

1. never use future realized liquidations to alter the current displayed map
2. only use them to update weights for **future** predictions
3. require the ensemble to beat each standalone branch on a rolling
   out-of-sample window before promoting it
4. ship it, if ever, as a separate predictive overlay or alerting model, not as
   a silent rewrite of `v1`

Current verdict:

- the idea is reasonable as an online/offline forecasting experiment
- it is **not** a reason to merge `v1` / `v2` / `v5` into one default
  liquidation map today
