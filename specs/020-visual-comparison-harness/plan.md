# Implementation Plan: Visual Comparison Harness

**Spec**: `specs/020-visual-comparison-harness/spec.md`
**Feature Type**: Shared validation infrastructure
**Branch**: master

## Summary

Abstract the current screenshot-validation pieces into a reusable harness that
can score local-vs-provider visual parity for both current liq-map specs and
future heatmap specs.

The key architectural rule is explicit separation between:

- product adapters (`liq-map`, `liq-heat-map`)
- renderer adapters (`plotly`, future `lightweight`)

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

### Renderer Decision

- `plotly` is the first renderer adapter and the only one assumed to exist today
- `lightweight` is not a default; it is a future adapter path for Counterflow-style pages
- no repo-wide Lightweight installation is required for this spec's planning phase

### Reference URLs

- Local liq-map: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local liq-heat-map: `http://localhost:8002/chart/derivatives/liq-heat-map/btcusdt/1w`
- CoinAnK liq-map: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- CoinAnK liq-heat-map: `https://coinank.com/chart/derivatives/liq-heat-map/btcusdt/7d`

## Architecture

```
product adapter
    +
renderer adapter
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
2. explicit product-adapter contract
3. explicit renderer-adapter contract
4. renderer-agnostic scoring output
5. adapter separation between data capture and screenshot comparison
6. future compatibility with Counterflow-style rendering

## Phases

1. Inventory existing tooling.
2. Define shared manifest and scoring contracts.
3. Define product and renderer adapter seams.
4. Integrate liq-map on `plotly` first.
5. Leave clean seams for `liq-heat-map` and Counterflow/`lightweight`.

## Execution Order

- Phase 1-2 can run immediately in parallel with `spec-018` / `spec-019`
- Phase 3-5 should assume at least one concrete calibrated local profile path exists, starting with `spec-018`
- Counterflow integration should wait for these seams rather than adding a parallel special-case path

## Risks

- over-abstracting too early
- mixing data-comparison concerns with screenshot-comparison concerns
- binding the harness too tightly to Plotly-specific DOM behavior
- treating OCR-based validation and DOM-stable screenshot capture as interchangeable when they are not
- letting `lightweight` concerns leak into the default `plotly` path too early
