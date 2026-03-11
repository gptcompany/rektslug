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

- Local liq-map matrix:
  - `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
  - `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
  - `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
  - `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- CoinAnK liq-map matrix:
  - `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d`
  - `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
  - `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1d`
  - `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1w`
- Local liq-heat-map example: `http://localhost:8002/chart/derivatives/liq-heat-map/btcusdt/1w`
- CoinAnK liq-heat-map example: `https://coinank.com/chart/derivatives/liq-heat-map/btcusdt/7d`
- Coinglass visual routes are not yet canonical for this spec's first cut and must not be assumed during MVP implementation

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

## First-Cut Contract

The first green implementation is intentionally narrow:

- provider pair: `local` vs `CoinAnK`
- product adapter: `liq-map`
- renderer adapter: `plotly`
- active matrix: `BTC/ETH x 1d/1w`

The harness still defines provider/product/renderer seams, but it should not wire a
live Coinglass visual adapter until canonical URLs and capture invariants are
documented in a future spec or runbook update.

Minimum manifest schema:

- `schema_version`, `run_id`, `product`, `renderer`
- `symbol`, `exchange`, exactly one of `timeframe` or `window`
- `viewport.width`, `viewport.height`
- `local.url`, `local.screenshot_path`, `local.capture_timestamp`, `local.ready`
- `provider.name`, `provider.url`, `provider.screenshot_path`
- `provider.capture_timestamp`, `provider.capture_mode`

Minimum score schema:

- `schema_version`, `run_id`, `product`, `renderer`, `provider`
- `status`, `score`, `max_score`, `pass_threshold`, `tier1_pass`
- `components`

First-cut score semantics:

- if any Tier-1 gate fails, total score = `0`
- otherwise total score = `tier2_points + tier3_points`
- `max_score = 100`
- `pass_threshold = 95`

## What Already Works

- liq-map screenshot validation between local and CoinAnK
- local heatmap page capture and readiness checks
- OCR-backed screenshot validation path for heatmap-like workflows
- provider capture/manifests that can be reused as metadata inputs

## What Needs Work

1. one shared manifest contract for screenshot-based runs
2. explicit product-adapter contract
3. explicit renderer-adapter contract
4. renderer-agnostic scoring output with explicit JSON schema and thresholds
5. adapter separation between data capture and screenshot comparison
6. runtime/report-size/timestamp gates for each run
7. future compatibility with Counterflow-style rendering

## Phases

1. Inventory existing tooling and lock the first-cut matrix.
2. Define shared manifest, score, and threshold contracts.
3. Write failing tests for manifest/adapters/score policy before implementation.
4. Integrate `liq-map` on `plotly` for local vs CoinAnK only.
5. Add extension seams for future `liq-heat-map`, Coinglass visual adapters, and Counterflow/`lightweight`.

## Execution Order

- Phase 1-2 can run immediately in parallel with `spec-018` / `spec-019`
- Phase 3 may begin once the contracts above are fixed and at least one concrete calibrated local profile path exists, starting with `spec-018`
- Phase 4-5 should assume the TDD RED tests already exist and should not add live Coinglass visual wiring without new canonical route documentation
- Counterflow integration should wait for these seams rather than adding a parallel special-case path

## Non-Functional Gates

- Single `liq-map + plotly` comparison pair under `120s`
- Manifest JSON + score JSON under `1 MB` combined
- Stable `schema_version` and deterministic artifact naming

## Edge Cases to Handle

- local page loads but Plotly chart never becomes ready
- CoinAnK native download unavailable and screenshot-crop fallback is used
- unsupported `product + renderer` or `timeframe/window` pair
- provider unreachable or login failure with partial-manifest output
- incompatible timeframe-style vs window-style comparison input

## Risks

- over-abstracting too early
- mixing data-comparison concerns with screenshot-comparison concerns
- binding the harness too tightly to Plotly-specific DOM behavior
- treating OCR-based validation and DOM-stable screenshot capture as interchangeable when they are not
- letting `lightweight` concerns leak into the default `plotly` path too early
- assuming a Coinglass visual liq-map path exists before the repo documents it
