# CoinGlass Hyperliquid Capture Manifest

As of: 2026-03-20

- Total runs with Hyperliquid endpoint observed: 23
- `timeframe_applied=true`: 11
- `timeframe_applied=false`: 8
- `timeframe_applied=null`: 4
- Hyperliquid symbols observed: BTC
- Hyperliquid `ETH` observed: no
- Binance per-exchange intervals observed in same runs: 1, 180d, 30, 365d, 5, 90d
- CoinGlass aggregated `exLiqMap` intervals observed in same runs: 1

## Key Findings

- All saved Hyperliquid requests use `/api/hyperliquid/topPosition/liqMap?symbol=BTC`; no saved `ETH` Hyperliquid capture was found in this inventory.
- In the saved runs, the Hyperliquid endpoint never carries an explicit `interval` parameter.
- When the UI timeframe is changed successfully for the Binance per-exchange map, the Binance `index/5/liqMap` request changes interval, but the Hyperliquid endpoint shape stays the same.
- The saved aggregate `index/2/exLiqMap` requests remain at `interval=1` in this inventory; this should not be over-interpreted as a CoinGlass product fact, because the current automation primarily rewrites the main per-exchange `index/5/liqMap` flow.
- For canonical Binance/CoinAnK/CoinGlass comparisons, the stable comparison windows remain `1d` and `1w` (`7 day` in CoinGlass UI). The broader candidate-window sweep is for Hyperliquid timeframe discovery only.

## Runs

| Run | Requested UI TF | Applied | Hyper Symbol | Binance Intervals | Aggregate Intervals | Summary |
| --- | --- | --- | --- | --- | --- | --- |
| 20260303T140645Z | - | None | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T140645Z/coinglass/summary.json` |
| 20260303T141655Z | - | None | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T141655Z/coinglass/summary.json` |
| 20260303T142724Z | - | None | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T142724Z/coinglass/summary.json` |
| 20260303T143204Z | - | None | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T143204Z/coinglass/summary.json` |
| 20260303T143413Z | 7 day | False | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T143413Z/coinglass/summary.json` |
| 20260303T143602Z | 7 day | True | BTC | 1, 5 | 1 | `data/validation/raw_provider_api/20260303T143602Z/coinglass/summary.json` |
| 20260303T143706Z | 7 day | True | BTC | 1, 5 | 1 | `data/validation/raw_provider_api/20260303T143706Z/coinglass/summary.json` |
| 20260303T143915Z | 1 day | True | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T143915Z/coinglass/summary.json` |
| 20260303T163818Z | 1 day | False | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T163818Z/coinglass/summary.json` |
| 20260303T164013Z | 1 day | False | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T164013Z/coinglass/summary.json` |
| 20260303T164114Z | 1 day | False | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T164114Z/coinglass/summary.json` |
| 20260303T164211Z | 1 day | False | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T164211Z/coinglass/summary.json` |
| 20260303T164322Z | 1 day | False | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T164322Z/coinglass/summary.json` |
| 20260303T164548Z | 1 day | False | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T164548Z/coinglass/summary.json` |
| 20260303T164646Z | 1 day | False | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T164646Z/coinglass/summary.json` |
| 20260303T165247Z | 7 day | True | BTC | 1, 5 | 1 | `data/validation/raw_provider_api/20260303T165247Z/coinglass/summary.json` |
| 20260303T165345Z | 1 day | True | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T165345Z/coinglass/summary.json` |
| 20260303T172006Z | 30 day | True | BTC | 1, 30 | 1 | `data/validation/raw_provider_api/20260303T172006Z/coinglass/summary.json` |
| 20260303T172122Z | 90 day | True | BTC | 1, 90d | 1 | `data/validation/raw_provider_api/20260303T172122Z/coinglass/summary.json` |
| 20260303T172217Z | 180 day | True | BTC | 180d | 1 | `data/validation/raw_provider_api/20260303T172217Z/coinglass/summary.json` |
| 20260303T172313Z | 1y | True | BTC | 1, 365d | 1 | `data/validation/raw_provider_api/20260303T172313Z/coinglass/summary.json` |
| 20260303T172412Z | 7 day | True | BTC | 5 | 1 | `data/validation/raw_provider_api/20260303T172412Z/coinglass/summary.json` |
| 20260303T174247Z | 1 day | True | BTC | 1 | 1 | `data/validation/raw_provider_api/20260303T174247Z/coinglass/summary.json` |
