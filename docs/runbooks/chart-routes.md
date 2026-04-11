# Chart Routes

This repo now has two canonical UI entrypoints for visual validation against
provider reference pages.

## Canonical Routes

- Liquidation map:
  `http://localhost:8002/chart/derivatives/liq-map/<exchange>/<symbol>/<timeframe>`
- Liquidation heatmap:
  `http://localhost:8002/chart/derivatives/liq-heat-map/<symbol>/<timeframe>`

## Canonical Liq-Map Surface Contract

The browser product route is always the canonical `liq-map` entrypoint. The
local API surface behind it is explicit:

| Exchange | `surface=public` API | `surface=legacy` API |
|----------|----------------------|----------------------|
| `binance` | `/liquidations/coinank-public-map` | `/liquidations/levels` |
| `bybit` | `/liquidations/coinank-public-map` | `/liquidations/levels` |
| `hyperliquid` | `/liquidations/hl-public-map` | unsupported |

Product-facing validation defaults to `surface=public`. The legacy
`/liquidations/levels` surface remains available for calibration and
model-inspection only; it is not the canonical product surface.

Binance and Bybit public responses expose machine-readable serving provenance:

- `serving_provenance`: `artifact-backed`, or `legacy-fallback` for Binance fallback serving
- `serving_artifact_model_id`: modeled artifact id when artifact-backed, else `null`
- `serving_artifact_snapshot_ts`: modeled artifact snapshot timestamp when artifact-backed, else `null`

## Current Liq-Map Reference Matrix

These are the exact Coinank `liq-map` paths that define the current 1:1 validation scope:

- `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d`
- `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1d`
- `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1w`

These are the corresponding local mirror paths that must stay aligned:

- `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`

Heatmap examples are documented separately and are not part of the active `liq-map` validation scope.

## Compatibility Aliases

These remain available, but should be considered legacy:

- `/coinglass`
- `/heatmap_30d.html`
- `/liq_map_1w.html`
- `/liq_map_1w/<symbol>`

## Timeframe Mapping

Only these chart timeframes are supported right now:

- `1d` -> `48h` (temporary closest internal window)
- `1w` -> `7d`

Any other chart timeframe should be treated as unsupported until the 1:1 validation baseline is stable.

## Validation Scripts

The visual validation scripts now target the canonical routes:

- `scripts/validate_liqmap_visual.py`
- `scripts/validate_heatmap_visual.py`
- `scripts/run_visual_harness.py`

Use these routes for browser automation, screenshot diffing, and future 1:1
provider validation loops.

For the current frozen `spec-020` MVP, the concrete live harness paths are:

```bash
uv run python scripts/run_visual_harness.py \
  --provider coinank \
  --product liq-map \
  --renderer plotly \
  --surface public \
  --symbol BTCUSDT \
  --timeframe 1d

uv run python scripts/run_visual_harness.py \
  --provider coinglass \
  --product liq-map \
  --renderer plotly \
  --surface public \
  --symbol ETHUSDT \
  --timeframe 1w
```

This is separate from the internal validation dashboard in
`frontend/validation_dashboard.html`, which tracks validation-pipeline health
rather than provider-parity artifacts.
