# Spec 017: Provider Liq-Map Comparison

## Overview

Operationalize a repeatable comparison workflow for **liq maps only** across:

- local `rektslug` canonical liq-map route
- CoinAnk `liq-map`
- Coinglass `liqMap`

This spec is intentionally narrow:

- product: `liq-map` only
- symbols: `BTCUSDT`, `ETHUSDT`
- timeframes: `1d`, `1w`

`liq-heat-map`, `LiquidityHeatmap`, and any heatmap-style 2D grid are explicitly
out of scope for this spec and should be handled by a future `spec-018`.

## Goals

1. Reuse the provider-capture and comparison tooling already present in the repo.
2. Freeze a clean reference matrix for `BTC`/`ETH` and `1d`/`1w`.
3. Produce auditable artifacts for every comparison run:
   - raw provider payloads
   - local/provider screenshots
   - normalized comparison report
   - machine-readable manifest
4. Make the workflow deterministic enough to support repeated provider checks and
   future regression baselines.

## Reference Sources

These repo documents/scripts are the source of truth for this workstream:

- `docs/runbooks/chart-routes.md`
- `docs/provider-api-comparison.md`
- `scripts/capture_provider_api.py`
- `scripts/compare_provider_liquidations.py`
- `scripts/provider_gap_analysis.py`
- `scripts/run_provider_api_comparison.py`
- `scripts/coinank_screenshot.py`
- `scripts/validate_liqmap_visual.py`

## Scope

### In Scope

- comparison of **liq-map** artifacts only
- local vs CoinAnk vs Coinglass
- `BTCUSDT` and `ETHUSDT`
- `1d` and `1w`
- native or scripted provider screenshot capture
- raw payload capture, normalization, diffing, and persisted manifests

### Out of Scope

- `liq-heat-map`
- `LiquidityHeatmap`
- CoinAnk `liq-heat-map`
- Coinglass liquidity or liquidation heatmap grids
- timeframes other than `1d` and `1w`
- symbols other than BTC/ETH
- frontend redesign work already covered by `spec-016`

## Reference Matrix

### Local / CoinAnk Mirror Routes

Canonical liq-map matrix already documented in `docs/runbooks/chart-routes.md`:

- Local BTC 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- Local BTC 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local ETH 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- Local ETH 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- CoinAnk BTC 1D: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d`
- CoinAnk BTC 1W: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- CoinAnk ETH 1D: `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1d`
- CoinAnk ETH 1W: `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1w`

### Coinglass Liq-Map References

Use the URLs and API endpoints already documented in `docs/provider-api-comparison.md`:

- documented page target for liq-map: `https://www.coinglass.com/pro/futures/LiquidationMap`
- provider API endpoint: `https://capi.coinglass.com/api/index/5/liqMap`

For this spec, only the documented `1d` and `1w` mappings matter:

- `1d -> interval=1, limit=1500`
- `1w -> interval=5, limit=2000`

## Runtime Assumptions

- `rektslug-api` and `rektslug-sync` are up and healthy
- DuckDB is caught up to the latest upstream values made available by the
  `ccxt-data-pipeline -> DuckDB` bridge
- `/liquidations/levels` returns non-empty arrays for BTC/ETH on the selected
  timeframe
- local Chromium / Playwright is available where browser capture is needed
- all provider secrets are loaded via `dotenvx`

## Credential Assumptions

Secrets are expected to exist in `dotenvx` with `COINANK_*` and/or
`COINGLASS_*` prefixes.

This spec does not redefine secret names; the scripts and existing docs remain
the source of truth for exact environment variable names.

## Non-Functional Requirements

- **NFR-001**: Provider capture (CoinAnk, Coinglass) MUST complete within 60 seconds per `(symbol, timeframe)` pair, including page load and screenshot.
- **NFR-002**: Raw payload artifacts SHOULD NOT exceed 10 MB per provider per run.
- **NFR-003**: The full 4-entry matrix run SHOULD complete within 10 minutes end-to-end.
- **NFR-004**: Artifact directory structure MUST be deterministic given the same `(symbol, timeframe, timestamp)` inputs.

## Edge Cases

- **EC-001**: Provider offline or returning HTTP 5xx — the workflow MUST log the failure, skip the provider, and continue with available providers.
- **EC-002**: Provider rate-limiting (HTTP 429) — the workflow SHOULD retry once after a backoff of at least 5 seconds; if still rate-limited, skip and log.
- **EC-003**: Empty payload from provider — the workflow MUST record the empty response as an artifact and flag it in the manifest rather than silently dropping it.
- **EC-004**: Provider URL drift (changed path or query parameters) — the workflow MUST fail loudly rather than silently fetching a different product (e.g., heatmap instead of liq-map).
- **EC-005**: Local `/liquidations/levels` returns empty for a supported pair — the run MUST still capture provider artifacts but flag the local gap in the comparison report.

## Functional Requirements

- **FR-001**: The workflow MUST compare only `liq-map` artifacts.
- **FR-002**: The workflow MUST support only `BTCUSDT` and `ETHUSDT`.
- **FR-003**: The workflow MUST support only `1d` and `1w`.
- **FR-004**: Every run MUST preserve raw provider payloads in a timestamped directory.
- **FR-005**: Every run MUST preserve screenshot artifacts for local and provider views.
- **FR-006**: CoinAnk screenshot capture SHOULD prefer the native chart download flow when available; the existing scripted screenshot path remains an acceptable fallback.
- **FR-007**: Coinglass capture MUST use the documented `liqMap` path only; heatmap endpoints are invalid for this spec.
- **FR-008**: Coinglass capture SHOULD prefer authenticated REST replay when available, with browser interception retained as fallback.
- **FR-009**: Every run MUST emit a manifest with provider URLs, timeframe, symbol, capture mode, and artifact paths.
- **FR-010**: Every run MUST emit a normalized comparison report that makes CoinAnk vs Coinglass vs local bucket differences inspectable.
- **FR-011**: The workflow MUST preserve enough metadata to replay or audit a run later, including timestamps, hashes, and provider-specific request metadata when available.
- **FR-012**: When running in persisted mode, the workflow SHOULD persist run summaries to a validation DuckDB table for longitudinal tracking across runs.

## Deliverables

1. A `liq-map`-only comparison workflow for `1d` and `1w`
2. Timestamped manifests under `data/validation/`
3. Normalized comparison reports for local, CoinAnk, and Coinglass
4. Baseline runs for:
   - BTC 1D
   - BTC 1W
   - ETH 1D
   - ETH 1W

## Success Criteria

- **SC-001**: A single documented workflow can produce artifacts for any one
  `(symbol, timeframe)` pair in the `BTC/ETH x 1d/1w` matrix.
- **SC-002**: Each run stores raw provider captures, screenshots, and a manifest
  without manual file renaming.
- **SC-003**: CoinAnk and Coinglass captures are both tied to explicit `liq-map`
  references, not heatmap substitutes.
- **SC-004**: The comparison output makes timeframe, provider, and capture mode
  explicit enough to avoid mixing `1d` and `1w` runs.
- **SC-005**: The repo can retain a baseline for all 4 matrix combinations
  without widening scope beyond `liq-map`.

## Implementation Notes

- `spec-016` remains the visual parity spec for the local CoinAnk-style page.
- `spec-017` starts only after the local liq-map route and preflight runtime
  gates are healthy enough to serve as a valid local comparison target.
- If a provider route drifts externally, the repo docs/scripts remain the
  reference to update, but the spec scope does not change.
