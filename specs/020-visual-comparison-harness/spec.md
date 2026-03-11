# Spec 020: Visual Comparison Harness

## Overview

Build a provider-agnostic visual comparison harness for charts and heatmaps that
produces repeatable screenshots, manifests, and machine-readable scoring.

This spec is infrastructure:

- it should serve `rektslug-ank`, `rektslug-glass`, and later heatmap work
- it does not define provider-specific model tuning itself
- it must keep **product adapters** separate from **renderer adapters**
- its first concrete green path is `local + CoinAnK + liq-map + plotly`

## Reference Sources

- `scripts/validate_liqmap_visual.py`
- `scripts/validate_heatmap_visual.py`
- `scripts/validate_screenshots.py`
- `scripts/coinank_screenshot.py`
- `scripts/capture_provider_api.py`
- `docs/provider-api-comparison.md`
- `docs/runbooks/chart-routes.md`
- `docs/ARCHITECTURE.md`
- `frontend/liq_map_1w.html`
- `frontend/coinglass_heatmap.html`

## Scope

### In Scope

- screenshot capture orchestration
- artifact manifests
- scoring/reporting schema
- provider/local viewport normalization
- reuse for both `liq-map` and later `liq-heat-map`
- product adapters
- renderer adapters
- a first concrete harness run for local vs CoinAnK `liq-map`

### Out of Scope

- provider-specific calibration logic
- heatmap model implementation
- Counterflow-specific profile behavior
- Coinglass visual wiring before canonical URLs/capture rules are documented

## Reference URLs

Current canonical liq-map validation matrix:

- Local `BTC 1d`: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- Local `BTC 1w`: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local `ETH 1d`: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- Local `ETH 1w`: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- CoinAnK `BTC 1d`: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d`
- CoinAnK `BTC 1w`: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- CoinAnK `ETH 1d`: `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1d`
- CoinAnK `ETH 1w`: `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1w`

Future extension references:

- Local liq-heat-map: `http://localhost:8002/chart/derivatives/liq-heat-map/btcusdt/1w`
- CoinAnK liq-heat-map: `https://coinank.com/chart/derivatives/liq-heat-map/btcusdt/7d`

Coinglass visual URLs are intentionally not listed here yet. The first cut of this
spec must not assume a canonical Coinglass liq-map visual route until that capture
path is documented by a follow-up spec or runbook update.

## Required Tools

- `uv`
- Python `playwright`
- Chromium installed via `uv run playwright install chromium`
- existing Plotly-based local pages already present in repo

## Adapter Model

The harness should use two independent adapter axes:

- **Product adapters**:
  - `liq-map`
  - `liq-heat-map`
- **Renderer adapters**:
  - `plotly`
  - `lightweight` (reserved for Counterflow-style integration)

This separation is required to avoid conflating:

- the dataset/product being validated
- the rendering technology used by the page under test

## Manifest and Score Contract

First-cut runs MUST emit one manifest JSON and one score JSON per comparison pair.

Required manifest fields:

- `schema_version`
- `run_id`
- `product`
- `renderer`
- `symbol`
- `exchange` when applicable
- exactly one of `timeframe` or `window`
- `viewport.width`
- `viewport.height`
- `local.url`
- `local.screenshot_path`
- `local.capture_timestamp`
- `local.ready`
- `provider.name`
- `provider.url`
- `provider.screenshot_path`
- `provider.capture_timestamp`
- `provider.capture_mode`

Required score fields:

- `schema_version`
- `run_id`
- `product`
- `renderer`
- `provider`
- `status`
- `score`
- `max_score`
- `pass_threshold`
- `tier1_pass`
- `components`

`components` is an array of objects, each with:

- `name`: string component identifier such as `tier1_ready` or `tier2_price_range`
- `pass`: boolean pass/fail result for the component
- `points`: awarded points, `0` when the component fails
- `max_points`: maximum points available for the component
- `detail`: optional human-readable explanation

For the first concrete `liq-map + plotly` path, the scoring formula reuses the
current `scripts/validate_liqmap_visual.py` contract:

- if any Tier-1 gate fails, total score = `0`
- otherwise total score = `tier2_points + tier3_points`
- `max_score = 100`
- `pass_threshold = 95`

The first implementation MUST preserve these semantics before introducing any
additional renderer-specific scoring model.

## Functional Requirements

- **FR-001**: The harness MUST support local-vs-provider visual capture with reproducible viewport parameters.
  Acceptance: the first green path captures one local screenshot and one provider screenshot at `1920x1400` with deterministic artifact names under a single `run_id`.
- **FR-002**: The harness MUST emit a manifest tying screenshots to symbol, timeframe/window, provider, product, and run timestamp.
  Acceptance: every comparison pair writes a JSON manifest containing all required manifest fields listed above.
- **FR-003**: The harness MUST emit machine-readable scores suitable for thresholding in CI/manual gates.
  Acceptance: every comparison pair writes a JSON score report containing all required score fields and returns non-zero when the pair fails the configured threshold.
- **FR-004**: The harness MUST support at least `liq-map` initially and be extensible to `liq-heat-map`.
  Acceptance: the first implementation ships with a concrete `liq-map` adapter and a documented `liq-heat-map` adapter contract without ad-hoc branching in the runner.
- **FR-005**: The harness MUST keep provider adapters separate from scoring logic.
  Acceptance: provider-specific capture code may populate normalized manifest fields, but the scorer consumes only the normalized manifest/report contract.
- **FR-006**: The harness MUST model product adapters separately from renderer adapters.
  Acceptance: configuration, manifest, and score output expose distinct `product` and `renderer` fields, and unsupported combinations fail before capture begins.
- **FR-007**: `plotly` MUST be treated as the first concrete renderer adapter.
  Acceptance: the first passing harness run is `product=liq-map`, `renderer=plotly`, `provider=coinank`.
- **FR-008**: `lightweight` MUST be introduced only as a separate renderer adapter, never as an implicit default.
  Acceptance: the spec may define a future `lightweight` adapter seam, but no first-cut task may require global Lightweight installation or treat it as the default renderer.

## Non-Functional Requirements

- **NFR-001**: A single screenshot-comparison pair for the `liq-map + plotly` MVP MUST complete in under `120s` when the local API is already healthy and Chromium is installed.
- **NFR-002**: The manifest JSON plus score JSON for a single comparison pair MUST remain under `1 MB` combined.
- **NFR-003**: Re-running the same matrix entry MUST preserve `schema_version` and field names, and artifact naming MUST remain deterministic under the same `run_id` convention.

## Success Criteria

- **SC-001**: A single `liq-map + plotly` run can capture local/CoinAnK screenshots and emit score + manifest without manual renaming.
- **SC-002**: The same manifest/score schema can be reused unchanged by `rektslug-ank`, `rektslug-glass`, and future heatmap specs.
- **SC-003**: The first-cut pass/fail rule is explicit enough to reproduce decisions: Tier-1 gate pass plus total score `>= 95/100`.

## Edge Cases

- **EC-001**: If the local API is healthy but the chart never reaches a ready state, the run MUST fail cleanly with `ready=false`, `tier1_pass=false`, and total score `0`.
- **EC-002**: If CoinAnK capture falls back from native download to screenshot crop, the run MAY continue but the manifest MUST record `provider.capture_mode`.
- **EC-003**: Unsupported `product + renderer` or `timeframe/window` combinations MUST fail before browser capture begins.
- **EC-004**: If the provider is unreachable or login fails irrecoverably, the run MUST exit non-zero and write a partial manifest with the failure reason instead of a false pass.
- **EC-005**: Timeframe-style runs and window-style runs MUST remain distinguishable in the manifest; scoring MUST reject incompatible pairings instead of coercing them silently.

## Notes

- Existing scripts like `scripts/validate_liqmap_visual.py` are starting points, not necessarily the final architecture.
- This harness should stay renderer-agnostic enough to support both Plotly pages and future Counterflow-style visual adapters.
- Phase 3+ assumes that `spec-018` or an equivalent prior spec has already established at least one calibrated local profile path. Phase 1-2 may proceed independently.
