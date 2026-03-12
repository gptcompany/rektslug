# Provider API Comparison Workflow

## Scope

This runbook documents the current workflow for capturing and comparing raw
liquidation data across external providers:

- CoinAnk
- Coinglass
- Bitcoin CounterFlow

The goal is to compare raw API payloads before making assumptions about how any
provider computes or visualizes liquidation maps.

## Current State

Two scripts now cover the workflow:

- `scripts/capture_provider_api.py`
- `scripts/compare_provider_liquidations.py`
- `scripts/provider_gap_analysis.py`
- `scripts/coinglass_decode_payload.js`

The first script captures raw JSON responses during page load with Playwright.
The second script reads one or more capture manifests, normalizes the most
relevant liquidation dataset per provider, and emits a comparison report.

A third script now orchestrates the full workflow:

- `scripts/run_provider_api_comparison.py`

For SQL-backed review of historical runs, there is also:

- `scripts/provider_comparison_sql_report.py`
- `scripts/provider_gap_sql_report.py`
- `scripts/coinglass_bundle_report.py`

This wrapper performs capture, normalization, comparison, report writing, and
optional DuckDB persistence in one command.

## Naming Convention

The repository uses `snake_case` for Python scripts under `scripts/`. The new
files follow that convention intentionally:

- `capture_provider_api.py`
- `compare_provider_liquidations.py`
- `provider_gap_analysis.py`

Do not rename these to kebab-case unless the whole script naming convention in
the repo changes. Kebab-case is acceptable for Markdown docs, so this file uses
`provider-api-comparison.md`.

## Capture Workflow

### 1. Capture provider traffic

Examples:

```bash
python3 scripts/capture_provider_api.py \
  --provider bitcoincounterflow
```

```bash
python3 scripts/capture_provider_api.py \
  --provider both \
  --coin BTC \
  --timeframe 1w \
  --coinglass-url "https://www.coinglass.com/..."
```

```bash
python3 scripts/capture_provider_api.py \
  --provider all \
  --coin BTC \
  --timeframe 1w \
  --coinglass-url "https://www.coinglass.com/..."
```

```bash
# CoinGlass via REST (no browser needed):
dotenvx run -f /media/sam/1TB/.env -- uv run python scripts/capture_provider_api.py \
  --provider both \
  --timeframe 1w \
  --coinglass-mode rest \
  --coinglass-url "https://www.coinglass.com/pro/futures/LiquidationMap"
```

The `--coinglass-mode` flag controls CoinGlass capture method:
- `browser` (default): Playwright route interception
- `rest`: direct REST API replay, no browser
- `auto`: try REST first, fallback to browser on failure

The manifest records both the requested mode (`args.coinglass_mode`) and the
actual mode used per provider (`capture_mode` in each provider summary).

Captures are written under:

`data/validation/raw_provider_api/<timestamp>/`

Each run contains:

- one subdirectory per provider
- `summary.json` per provider
- `manifest.json` for the whole run

Each captured response now also preserves the small header subset needed for
future provider-specific decoding:

- Coinglass response headers such as `user`, `time`, `v`, `encryption`
- the request header `cache-ts-v2` when present

### 2. Compare captured payloads

```bash
python3 scripts/compare_provider_liquidations.py \
  --manifest data/validation/raw_provider_api/<timestamp>/manifest.json
```

If no manifest is provided, the script uses the latest capture run.

Reports are written under:

`data/validation/provider_comparisons/`

### 2b. Query historical comparisons from DuckDB

```bash
python3 scripts/provider_comparison_sql_report.py
```

Use `--json` for machine-readable output or `--db-path` to point at a
non-default DuckDB.

For the residual-gap scenarios:

```bash
python3 scripts/provider_gap_sql_report.py
```

This reads `provider_gap_analysis_*` and shows the latest scenario ratios plus
the latest leverage composition snapshots.

For the local CoinGlass frontend bundle health:

```bash
python3 scripts/coinglass_bundle_report.py --persist-db
```

This computes the local `_app-*.js` bundle SHA-256, checks whether the current
TOTP/AES constants are still present verbatim, and stores the observation in
DuckDB for drift tracking.

### 2c. Quantify the residual provider gap

```bash
python3 scripts/provider_gap_analysis.py \
  --manifest data/validation/raw_provider_api/<timestamp>/manifest.json \
  --persist-db
```

This script reuses the exact `getLiqMap` / `liqMap` payloads already captured by
the workflow, then persists scenario-level normalization metrics into DuckDB.

The current scenario set is:

- `raw`
- `coinank_common_tiers`
- `coinank_rebinned_to_coinglass_step`
- `coinank_common_tiers_rebinned`

The last scenario is the most defensible apples-to-apples basis currently
available because it aligns leverage coverage first and price granularity
second.

### 3. Run the full workflow in one command

```bash
python3 scripts/run_provider_api_comparison.py \
  --provider all \
  --coin BTC \
  --timeframe 1w
```

By default, this command also persists normalized comparison rows into the
validation DuckDB (`data/validation/validation_results.duckdb`). Use
`--no-persist-db` if you want a file-only run.

## Calibration Commands

### Spec-019: Coinglass-oriented liq-map calibration

`spec-019` reuses frozen Coinglass references from `spec-017`, then compares a
fresh local baseline (`rektslug-default`) and the candidate
`rektslug-glass` profile against those same provider artifacts.

Standard run:

```bash
uv run python scripts/run_glass_calibration.py
```

If you want to point the runner at a non-container local API instance:

```bash
REKTSLUG_API_BASE=http://127.0.0.1:8010 \
  uv run python scripts/run_glass_calibration.py
```

The accepted calibration artifact is currently:

`data/validation/provider_comparisons/20260311T005526Z_calibration_rektslug-glass.json`

## Provider-Specific Notes

### CoinAnk

- Capture is page-driven and reuses the existing CoinAnk login flow.
- The public page now shows two relevant liq-map endpoints:
  - `getLiqMap?exchange=...&symbol=...&interval=...`
  - `getAggLiqMap?baseCoin=...&interval=...`
- `getLiqMap` is now the preferred parser because it is symbol-specific and
  exposes explicit leverage ladders on the public payload (`x25` through `x100`).
- Those public ladders do **not** include `x5` or `x10`, which is a concrete
  explanation for why CoinAnk can look materially smaller than a model that
  includes low-leverage tiers.
- Even on `getLiqMap`, long/short are still inferred structurally by splitting
  the shared price grid at `lastIndex` (or `lastPrice` as fallback), because the
  payload does not expose separate long and short arrays.
- `getAggLiqMap` remains useful as a fallback, but it is now secondary.

### Coinglass

- Capture requires an explicit `--coinglass-url`.
- The project now supports authenticated Coinglass capture via
  `dotenvx run -f /media/sam/1TB/.env -- ...` using:
  - `COINGLASS_USER_LOGIN`
  - `COINGLASS_USER_PASSWORD`
- Headless capture must mask `navigator.webdriver`; otherwise Coinglass can
  return a misleading `404 Not Found` instead of the real page.
- The default capture target remains the public
  `https://www.coinglass.com/LiquidationData` page.
- The apples-to-apples route for CoinAnk `liq-map` is now:
  - `https://www.coinglass.com/pro/futures/LiquidationMap`
- That route does **not** encode the timeframe in the URL.
- The script now applies the timeframe via **Playwright route interception**
  (as of commit `cae0e8f`). Instead of clicking the dropdown, it intercepts
  the page's own authenticated `liqMap` request and rewrites the `interval`,
  `limit`, and `data` query parameters before forwarding.
- `timeframe_applied` is set to `true` only when a rewritten response is
  captured with matching `interval`/`limit` and `success: true` in the body.
- All 6 timeframes have been verified with real captures (2026-03-03):
  - `1d -> interval=1, limit=1500`
  - `1w -> interval=5, limit=2000`
  - `1m -> interval=30, limit=1440`
  - `3m -> interval=90d, limit=1440`
  - `6m -> interval=180d, limit=1440`
  - `1y -> interval=365d, limit=1440`
- The `data` parameter is generated in Python using the same TOTP+AES
  mechanism as the CoinGlass frontend (reverse-engineered from `_app` bundle).
- On reload, the page first loads the default `interval=1` request, then
  the route handler rewrites subsequent requests with the desired params.
  The comparison script keeps the later, higher-priority capture.
- **Browserless REST replay** (added 2026-03-03): The full auth mechanism has
  been decoded. Login is a simple `POST` to
  `capi.coinglass.com/coin-community/api/user/login` returning an
  `accessToken` (~27h TTL). The token is sent as the `Obe` header on API
  calls. Use `--coinglass-mode rest` to skip Playwright entirely for
  CoinGlass. Parity verified: REST and browser produce identical payloads
  for the same timeframe.
- The provider-specific BTCUSDT liquidation map endpoint is:
  - `capi.coinglass.com/api/index/5/liqMap?...`
- Once decoded, the payload exposes:
  - `lastPrice`
  - `instrument`
  - `liqMapV2`
- `liqMapV2` is a dictionary keyed by top-level price bucket, where each value
  is a list of clusters shaped like `[price, value, leverage, heat_band]`.
- The comparison script now parses this endpoint explicitly as
  `liquidation_heatmap / price_bins` by summing the cluster values inside each
  top-level bucket.
- For the public BTCUSDT heatmap-style grid, use this explicit override:
  - `--coinglass-url https://www.coinglass.com/LiquidityHeatmap`
- That page exposes a direct 2D endpoint:
  - `capi.coinglass.com/liquidity-heatmap/api/liquidity/v4/heatmap`
- The endpoint shape is:
  - `[timestamp_seconds, [[price, intensity], ...]]`
- This route is a **liquidity** heatmap, not a liquidation heatmap. It is useful for
  shape analysis and reverse engineering, but it is not a 1:1 substitute for a
  liquidation map.
- The comparison script now parses that 2D payload explicitly and collapses it
  into aggregate per-price bins for rough cross-provider shape comparison.
- It also derives `current_price` from companion Coinglass `ticker` or `kline`
  captures in the same manifest, so the below-price / above-price split is not
  guessed blindly.
- The more relevant Coinglass route for heatmap-vs-heatmap work remains:
  - `https://www.coinglass.com/pro/futures/LiquidationHeatMapNew`
- That page calls:
  - `capi.coinglass.com/api/index/v5/liqHeatMap?...`
- The endpoint is encrypted, but the decoder now handles payloads large enough
  for this route by passing ciphertext through a temp file instead of a CLI arg.
- Once decoded, the payload exposes:
  - `prices`: visible time columns
  - `y`: price rows
  - `liq`: sparse `[x_index, y_index, value]` cells
- The comparison script now normalizes this endpoint by taking the latest
  visible x-column only, which gives a current-state `price_bins` view that is
  much closer to CoinAnk's `getLiqMap` than the public routes.
- Other public Coinglass endpoints often return an encoded string in `data`.
- `scripts/compare_provider_liquidations.py` now has a header-aware decode path
  for Coinglass, but it only works when the capture includes the required
  response headers and a local `_app-*.js` bundle is available.
- `scripts/coinglass_decode_payload.js` mirrors the site decoder by loading the
  bundled frontend `CryptoJS` and `pako` modules directly from the saved
  Coinglass bundle.
- If the capture is missing `user`/`v` (or the bundle), the parser falls back
  to envelope metadata only.

### Bitcoin CounterFlow

- `scripts/capture_provider_api.py` explicitly triggers a fetch for
  `/api/liquidations`.
- The endpoint is not fully public. It returns `403` without an allowed
  `Origin`.
- It returns `200` when called from:
  - `https://bitcoincounterflow.com`
  - the extension origin
- The comparison script parses this payload explicitly as a USD-notional
  liquidation time-series.

Important distinction:

- `api/liquidations` is a raw time-series feed
- the website/extension `Liquidation Heatmap` view also has a client-side
  synthetic heatmap path built from proxied Binance klines

Do not assume these two views are the same dataset.

Counterflow architectural role:

- explicit provider key: `bitcoincounterflow`
- explicit display name: `Bitcoin CounterFlow`
- roles: `data-source` and `visual-reference`
- expected future visual-harness entry: `renderer_adapter=lightweight`

Current repo decision:

- Counterflow is comparison-ready today on the raw data side
- Counterflow is not yet wired as a live visual-harness provider
- if that visual path is implemented later, it should plug into the shared
  harness through the `lightweight` renderer seam instead of a special-case
  global workflow

## What Is Still Missing

The workflow is usable, but it is not complete yet.

The main missing pieces are:

1. A better CoinAnk endpoint with explicit long/short separation
2. Stable Coinglass captures that include whatever headers are required for
   full numeric decode on secondary endpoints such as `exLiqMap`
3. `LiquidationHeatMapNew` still uses the latest visible column, which is the
   best current approximation of "current state", but the UI semantics may
   still involve additional persistence rules
4. Optional historical aggregation across many capture runs
5. Monitoring for CoinGlass bundle hash changes (current: `_app-94ee9e72c1d2190a.js`).
   If the bundle updates, the TOTP secret and AES key may need re-extraction

Today, Bitcoin CounterFlow, CoinAnk, and Coinglass all have provider-specific
parsers.

CoinAnk now has provider-specific parsers for both `getLiqMap` and
`getAggLiqMap`.

`getLiqMap` is preferred because it exposes symbol-level leverage ladders, but
its long/short split is still inferred from the shared price grid because the
payload does not expose separate long and short arrays.

Coinglass now has:

- a provider-specific parser for the public 2D `liquidity/v4/heatmap` payload
- a provider-specific parser for the current encoded response envelope
- a header-aware decode path for encrypted responses

Numeric decoding of the encrypted responses still depends on capturing the
provider headers that drive the site's decrypt flow.

## DuckDB: Needed or Not?

DuckDB is already part of this repository and already stores the core project
data.

The real question here is narrower:

- should the provider-comparison workflow stay file-based for now
- or should it also persist normalized comparison data into the existing DuckDB

That decision has now been split in two:

- the base comparison workflow can still be used file-first during discovery
- the residual-gap workflow now has a targeted DuckDB-backed layer because the
  CoinAnk vs CoinGlass `liqMap` schema is stable enough for repeatable
  scenario analysis

JSON files are still the source of truth for raw payloads, but the validation
DuckDB is now the right place for repeated, cross-run questions such as:

- comparing many days of captures
- joining provider snapshots by rounded timestamp
- tracking drift in totals, peaks, and bucket counts over time
- building aggregate statistics across dozens or hundreds of runs

Recommended rule:

- Use JSON first for discovery and parser development
- Reuse the existing validation DuckDB after provider schemas are stable enough
  to justify a tabular model

When that threshold is reached, prefer adding comparison tables to the current
validation DuckDB instead of introducing a separate storage system.

## DuckDB Tables

When DuckDB persistence is enabled, the workflow now creates and updates these
tables in the validation DuckDB:

- `provider_comparison_runs`
- `provider_comparison_datasets`
- `provider_comparison_pairs`
- `provider_gap_analysis_runs`
- `provider_gap_analysis_scenarios`
- `provider_gap_analysis_leverage`

These tables are intended for normalized provider-comparison metadata only.
They do not replace the raw JSON capture artifacts stored on disk.

## spec-017: Liq-Map-Only Comparison

`spec-017` narrows the comparison workflow to **liq-map only** across BTC/ETH and 1d/1w.

### New CLI flags

```bash
# Constrain to spec-017 matrix (BTC/ETH x 1d/1w)
--matrix-preset spec-017

# Filter comparison output to liq-map only (default)
--product liq-map

# Use REST replay for Coinglass (now default in orchestrator)
--coinglass-mode rest
```

### Quick run (single entry)

```bash
dotenvx run -f /media/sam/1TB/.env -- uv run python scripts/run_provider_api_comparison.py \
  --provider both --coin BTC --timeframe 1w --exchange binance \
  --coinglass-mode rest \
  --coinglass-url "https://www.coinglass.com/pro/futures/LiquidationMap" \
  --product liq-map --matrix-preset spec-017
```

### Full matrix run

```bash
for coin in BTC ETH; do
  for tf in 1d 1w; do
    dotenvx run -f /media/sam/1TB/.env -- uv run python scripts/run_provider_api_comparison.py \
      --provider both --coin "$coin" --timeframe "$tf" --exchange binance \
      --coinglass-mode rest \
      --coinglass-url "https://www.coinglass.com/pro/futures/LiquidationMap" \
      --product liq-map --matrix-preset spec-017
    sleep 10
  done
done
```

### Artifact checklist

After a run, verify:
- [ ] `manifest.json` contains `"product": "liq-map"`
- [ ] No capture URLs contain `heatmap`, `heat-map`, or `liqHeatMap`
- [ ] CoinAnk page_url uses `/liq-map/` path (not `/liq-heat-map/`)
- [ ] Coinglass source_url uses `/liqMap` endpoint (not `/liqHeatMap`)

## Recommended Next Steps

1. Run periodic `both` captures across multiple timeframes to build a baseline
   dataset for drift analysis.
2. Use `scripts/provider_comparison_sql_report.py` to watch drift across runs
   in `provider_comparison_*`.
3. Use `scripts/provider_gap_analysis.py` to track how much of the remaining
   CoinAnk vs CoinGlass gap is explained by leverage-tier coverage vs
   provider-side scaling.
4. Monitor bundle hash changes on CoinGlass because the REST replay still
   depends on constants reverse-engineered from the frontend bundle.
