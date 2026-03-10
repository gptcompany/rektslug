# Spec 020: Visual Comparison Harness

## Overview

Build a provider-agnostic visual comparison harness for charts and heatmaps that
produces repeatable screenshots, manifests, and machine-readable scoring.

This spec is infrastructure:

- it should serve `rektslug-ank`, `rektslug-glass`, and later heatmap work
- it does not define provider-specific model tuning itself

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

### Out of Scope

- provider-specific calibration logic
- heatmap model implementation
- Counterflow-specific profile behavior

## Reference URLs

- Local liq-map: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local liq-heat-map: `http://localhost:8002/chart/derivatives/liq-heat-map/btcusdt/1w`
- CoinAnK liq-map: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- CoinAnK liq-heat-map: `https://coinank.com/chart/derivatives/liq-heat-map/btcusdt/7d`

## Required Tools

- `uv`
- Python `playwright`
- Chromium installed via `uv run playwright install chromium`
- existing Plotly-based local pages already present in repo

## Functional Requirements

- **FR-001**: The harness MUST support local-vs-provider visual capture with reproducible viewport parameters.
- **FR-002**: The harness MUST emit a manifest tying screenshots to symbol, timeframe/window, provider, product, and run timestamp.
- **FR-003**: The harness MUST emit machine-readable scores suitable for thresholding in CI/manual gates.
- **FR-004**: The harness MUST support at least `liq-map` initially and be extensible to `liq-heat-map`.
- **FR-005**: The harness MUST keep provider adapters separate from scoring logic.

## Success Criteria

- **SC-001**: A single run can capture local/provider screenshots and emit score + manifest without manual renaming.
- **SC-002**: The same harness can be reused by `rektslug-ank`, `rektslug-glass`, and future heatmap specs.
- **SC-003**: Thresholds and metrics are explicit enough to decide pass/fail reproducibly.

## Notes

- Existing scripts like `scripts/validate_liqmap_visual.py` are starting points, not necessarily the final architecture.
- This harness should stay renderer-agnostic enough to support both Plotly pages and future Counterflow-style visual adapters.
