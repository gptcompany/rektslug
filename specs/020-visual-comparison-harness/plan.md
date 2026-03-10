# Implementation Plan: Visual Comparison Harness

**Spec**: `specs/020-visual-comparison-harness/spec.md`
**Feature Type**: Shared validation infrastructure
**Branch**: master

## Summary

Abstract the current screenshot-validation pieces into a reusable harness that
can score local-vs-provider visual parity for both current liq-map specs and
future heatmap specs.

## Technical Context

### Existing Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| `scripts/validate_liqmap_visual.py` | Exists | Local/CoinAnK liq-map visual validation |
| `scripts/validate_heatmap_visual.py` | Exists | Local heatmap capture/validation path |
| `scripts/validate_screenshots.py` | Exists | OCR/score path for screenshot comparison |
| `scripts/coinank_screenshot.py` | Exists | Provider screenshot capture |
| `scripts/capture_provider_api.py` | Exists | Raw capture + manifest scaffolding |
| provider comparison manifests | Exists | Good starting point for shared artifact schema |
| Playwright tooling | Exists | Can capture provider and local pages |

### Source Documents

- `docs/provider-api-comparison.md`
- `docs/runbooks/chart-routes.md`
- `docs/ARCHITECTURE.md`
- `specs/016-liqmap-1to1-coinank/plan.md`
- `specs/017-liqmap-provider-comparison/plan.md`

### Required Tools

- `uv`
- Python `playwright`
- Chromium via `uv run playwright install chromium`
- current local Plotly pages at `frontend/liq_map_1w.html` and `frontend/coinglass_heatmap.html`

### Reference URLs

- Local liq-map: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local liq-heat-map: `http://localhost:8002/chart/derivatives/liq-heat-map/btcusdt/1w`
- CoinAnK liq-map: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- CoinAnK liq-heat-map: `https://coinank.com/chart/derivatives/liq-heat-map/btcusdt/7d`

## Architecture

```
product adapter
    +
capture runner
    +
manifest writer
    +
scoring engine
    ->
visual comparison report
```

## What Already Works

- liq-map screenshot validation between local and CoinAnK
- local heatmap page capture and readiness checks
- OCR-backed screenshot validation path for heatmap-like workflows
- provider capture/manifests that can be reused as metadata inputs

## What Needs Work

1. one shared manifest contract for screenshot-based runs
2. renderer-agnostic scoring output
3. adapter separation between data capture and screenshot comparison
4. future compatibility with Counterflow-style rendering

## Phases

1. Inventory existing tooling.
2. Define shared manifest and scoring contracts.
3. Integrate liq-map first.
4. Leave clean adapter seams for heatmap and Counterflow.

## Risks

- over-abstracting too early
- mixing data-comparison concerns with screenshot-comparison concerns
- binding the harness too tightly to Plotly-specific DOM behavior
- treating OCR-based validation and DOM-stable screenshot capture as interchangeable when they are not
