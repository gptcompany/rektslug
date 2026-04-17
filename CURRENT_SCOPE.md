# Current Scope

This repository must be worked in strict sequence.

## Completed Foundation

`spec-030`, `spec-031`, `spec-032`, and `spec-033` are implemented.

- `spec-030`: deterministic Binance/Bybit modeled-snapshot producer contract
- `spec-031`: unified Binance/Bybit public CoinAnK-style serving layer
- `spec-032`: canonical public-vs-legacy liq-map surface hardening
- `spec-033`: public liq-map provider parity (Binance primary, CoinAnK default)

These specs do **not** mean the whole repo backlog is closed.

## Explicit Open Backlog

The following remain open and should be treated as separate backlog tracks:

- `spec-030` follow-up: Bybit historical 3TB-WDC reader / normalizer bridge for historical-only windows
- Root worktree backlog in `tasks.md`:
  reserved-margin validation and portfolio-margin solver
- WebSocket backlog in:
  - `specs/011-realtime-streaming/`

Do not infer that these are complete just because the Binance/Bybit liq-map serving path is now implemented.

## Active Workstream

Current priority is **liq-map only**.

Within `liq-map`, the exchange is a **variant axis**:

- `binance`
- `bybit`
- `hyperliquid`

This means exchange selection must be treated as a parameter of the same product, not as a separate parallel project.

Operationally, the current baseline remains **Binance first** until the liq-map
meets the spec-033 CoinAnK public provider-parity gate on the reference route.
Only after that should work expand to the exchange variants.

Use these as the only primary references unless a task explicitly says otherwise:

- Canonical route:
  `http://localhost:8002/chart/derivatives/liq-map/<exchange>/<symbol>/<timeframe>`
- Primary frontend:
  `frontend/liq_map_1w.html`
- Primary validation script:
  `scripts/validate_liqmap_visual.py`
- Primary API payloads:
  - `/liquidations/coinank-public-map` for Binance / Bybit public liq-map views
  - `/liquidations/hl-public-map` for Hyperliquid
  - `/liquidations/levels` remains the legacy fallback surface

For Binance and Bybit public liq-map responses, inspect
`serving_provenance`: `artifact-backed` means the public route served a modeled
snapshot artifact, while `legacy-fallback` means Binance public serving used
the legacy DuckDB builder fallback.

Current reference matrix for the active `liq-map` workstream:

Coinank reference paths:

- `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d`
- `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1d`
- `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1w`

Local mirror paths:

- `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`

The only active liq-map timeframes are:

- `1d`
- `1w`

## Deferred Workstream

`liq-heat-map` is explicitly **phase 2**.

Do not treat these as active implementation targets unless the task explicitly asks for heatmap work:

- `frontend/coinglass_heatmap.html`
- `scripts/validate_heatmap_visual.py`
- `/chart/derivatives/liq-heat-map/...`
- `/liquidations/heatmap-timeseries`

When heatmap work starts, the canonical route shape is:

- `http://localhost:8002/chart/derivatives/liq-heat-map/<symbol>/<timeframe>`

For heatmap, the active path axes are:

- `symbol` (for example `btcusdt`, `ethusdt`)
- `timeframe` (currently `1d`, `1w`)

There is no exchange segment in the canonical heatmap route.

## Legacy / Reference-Only

The following remain in the repo only as historical reference or compatibility surface:

- `frontend/heatmap.html`
- `frontend/heatmap_30d.html`
- `frontend/liquidation_map.html`
- `frontend/compare.html`
- `frontend/historical_liquidations.html`
- `/coinglass`
- `/heatmap_30d.html`
- `/liq_map_1w.html`

## Working Rule

When a new request is ambiguous, default to the active workstream above and ignore deferred or legacy references.

If a request mentions exchange variants without further detail:

- default to `binance`
- keep the work inside `liq-map`
- do not branch into `liq-heat-map`
