# Plan: Spec 023 — ETH Production Validation

## Approach

This is a **validation-only** spec. No new code is needed — the public builder
already supports ETHUSDT. The work is: run the builder, verify output structure,
capture screenshots, compare against CoinAnK reference, and document results.

## Phases

### Phase 1: Structural Validation (automated)

Call the public builder for all 4 ETH combos and verify response shape.

**Files involved** (read-only):
- `src/liquidationheatmap/api/public_liqmap.py` — builder
- `src/liquidationheatmap/api/routers/liquidations.py` — endpoint

**Deliverable**: Test file `tests/validation/test_eth_public_builder.py` with
structural assertions for ETHUSDT 1d/1w.

### Phase 2: Provider Comparison Baselines

Re-run the spec-017 comparison workflow for ETH 1d and ETH 1w.

**Files involved**:
- `scripts/run_provider_api_comparison.py` — orchestrator
- `scripts/capture_provider_api.py` — CoinAnK/Coinglass capture
- `data/validation/` — output artifacts

**Deliverable**: Fresh baseline manifests for ETH 1d/1w under `data/validation/`.

### Phase 3: Visual Validation

Capture screenshots of local ETH route and CoinAnK reference, compare visually.

**Files involved**:
- `scripts/validate_liqmap_visual.py` — screenshot + scoring
- `scripts/coinank_screenshot.py` — CoinAnK capture
- `frontend/liq_map_1w.html` — render target

**Deliverable**: Screenshots + visual similarity score in `data/validation/`.

### Phase 4: Results Documentation

Write `specs/023-eth-production-validation/validation-results.md` with metrics.

## Dependencies

- Running API instance (`rektslug-api` container or local `uvicorn`)
- Fresh ETH OI data in DuckDB
- CoinAnK credentials for screenshot capture (spec-017 prerequisite)

## Risk

- If ETH data is stale (`is_stale_real_data=true`), validation results are unreliable.
  Mitigation: run gap-fill before validation.
- CoinAnK login may fail (known flakiness). Mitigation: retry up to 3x, use cached
  reference if available.
