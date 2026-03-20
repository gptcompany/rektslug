# CoinGlass Hyperliquid Live Findings

As of: 2026-03-20

## Scope

This note combines two evidence sources:
- Saved repo captures under `data/validation/raw_provider_api`
- A live Playwright MCP spot-check on 2026-03-20 against `https://www.coinglass.com/pro/futures/LiquidationMap`

## Historical Inventory

- The saved capture inventory contains 23 CoinGlass LiquidationMap runs with a Hyperliquid request.
- In those saved runs, every observed Hyperliquid request is `GET /api/hyperliquid/topPosition/liqMap?symbol=BTC`.
- No saved Hyperliquid `ETH` request was found in the historical inventory.
- See:
  - `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.json`
  - `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.md`

## BTC Decode Audit

- A decode audit over the saved Hyperliquid `BTC` captures succeeded for 15 out of 23 runs.
- The successful payload shape is not a pre-bucketed heatmap. It is a JSON object with:
  - `price`
  - `list`
- The `list` entries are position-like records with fields such as:
  - `coin`
  - `entryPrice`
  - `leverage`
  - `liquidationPrice`
  - `margin`
  - `positionType`
  - `positionUsd`
  - `size`
  - `unrealizedPnl`
  - `updateTime`
  - `userId`
- This strongly suggests the Hyperliquid endpoint is closer to a top-positions/top-position-risk feed than to a final liq-map bucket series.
- See:
  - `data/validation/manifests/coinglass_hyperliquid_decode_audit_20260320.json`

## Live Playwright Spot-Check

On 2026-03-20, the Hyperliquid selector on the CoinGlass LiquidationMap page exposed more than `BTC` and `ETH`.
Observed options included, at minimum:
- `ETH`
- `BTC`
- `LINK`
- `HYPE`
- `XRP`
- `SOL`
- `ADA`
- `SUI`
- `DOGE`
- `TIA`

Therefore, the statement "CoinGlass Hyperliquid only exposes BTC and ETH" is not correct for the current live page state on 2026-03-20.

## Live ETH Request Evidence

A live Playwright MCP interception on 2026-03-20 captured:
- `GET https://capi.coinglass.com/api/hyperliquid/topPosition/liqMap?symbol=ETH`
- HTTP status `200`
- Response headers included:
  - `encryption: true`
  - `time: 1774025460280`
  - `user: H19OYuYa2xJLO+kBLcTykKL29l+deff4uJv7qbaIt2The1DGqyEIqsQy7QMEWG/P`
  - `v: 2`
- Response body shape:
  - top-level keys: `code`, `msg`, `data`, `success`
  - `data` is an encrypted string payload
  - observed encrypted data length: `19180`

## Interpretation

- Historical saved evidence proves repeatable `BTC` Hyperliquid capture.
- Live evidence proves `ETH` exists and that the current selector exposes multiple Hyperliquid symbols beyond `BTC` and `ETH`.
- The successful `BTC` decodes indicate the endpoint payload is position-centric, not a ready-made heatmap distribution.
- For spec and implementation purposes, it is still reasonable to keep initial parity work focused on `BTC` and `ETH`, but the spec should not assume the CoinGlass Hyperliquid universe is limited to those two symbols.

## Comparison Windows

- Canonical Binance/CoinAnK/CoinGlass comparisons should stay on `1d` and `1w` (`7 day` in the CoinGlass UI).
- The wider candidate-window sweep remains a Hyperliquid-only discovery tool until CoinGlass Hyperliquid timeframe semantics are bounded.
