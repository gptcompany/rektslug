# Implementation Plan: Rektslug-Ank Calibration

**Spec**: `specs/018-rektslug-ank-calibration/spec.md`
**Feature Type**: Local model calibration
**Branch**: master

## Summary

Turn the already-working `spec-017` comparison harness into a provider-specific
tuning loop for CoinAnK. The output is a dedicated `rektslug-ank` profile, not a
new capture pipeline.

## Technical Context

### Existing Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| `scripts/run_provider_api_comparison.py` | Exists | Runs local vs provider matrix |
| `scripts/capture_provider_api.py` | Exists | Handles local + CoinAnK capture orchestration |
| `scripts/compare_provider_liquidations.py` | Exists | Emits comparable liq-map metrics |
| `scripts/provider_gap_analysis.py` | Exists | Gap analysis on same artifacts |
| `scripts/coinank_screenshot.py` | Exists | Native/fallback CoinAnK screenshot capture |
| `scripts/validate_liqmap_visual.py` | Exists | Visual spot-check path if needed |
| `data/validation/provider_comparisons/` | Exists | Baseline reports from `spec-017` |

### Source Documents

- `docs/provider-api-comparison.md`
- `docs/runbooks/chart-routes.md`
- `specs/017-liqmap-provider-comparison/spec.md`
- `specs/017-liqmap-provider-comparison/plan.md`

### Required Environment Variables

- `COINANK_USER`
- `COINANK_PASSWORD`

### Reference URLs

- Local BTC 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- Local BTC 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local ETH 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- Local ETH 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- CoinAnK page matrix: see `docs/runbooks/chart-routes.md`

### Required Tools

- `uv run python ...`
- `dotenvx run -f /media/sam/1TB/.env -- ...`
- Playwright/Chromium only for screenshot spot-checks, not as the primary calibration metric

## Working Assumption

The current local model remains the default baseline. `rektslug-ank` is a
separate selectable profile layered on top.

## Architecture

```
default local profile
        +
provider comparison reports from spec-017
        ->
parameter sweep / calibration decisions
        ->
versioned profile: rektslug-ank
        ->
rerun spec-017 matrix against CoinAnK
```

## What Already Works

- deterministic local vs CoinAnK capture and comparison
- raw artifacts and pairwise reports for `BTC/ETH x 1d/1w`
- manifest/report infrastructure that can preserve active profile metadata once added

## What Needs Work

1. explicit local profile surface
2. versioned calibration parameter storage
3. acceptance thresholds for provider-specific parity
4. regression tests proving default profile isolation
5. explicit fallback behavior when no candidate clears the acceptance rule
6. explicit validation of runtime/report-size budgets from the spec NFRs

## Acceptance & Operational Gates

The implementation should follow the calibrated-profile acceptance rule from the
spec, not an informal "looks better" judgment:

- improve at least `3/5` core metrics
- on at least `3/4` matrix entries
- with no critical regression (`> 30%` degradation) on any remaining entry

Operational gates that must be checked during validation:

- full calibration matrix run completes in `< 10 minutes`
- emitted calibration report stays `< 1 MB`
- reports remain JSON and preserve profile/timestamp metadata
- if no candidate clears the rule, fall back to `rektslug-default` and write a
  machine-readable failure report

## Phases

1. Audit `spec-017` CoinAnK gaps and define target metrics.
2. Add explicit profile-selection plumbing.
3. Run calibration loops per matrix entry, keep only improving candidates, and
   invoke the explicit no-improvement fallback when needed.
4. Freeze one provider-specific profile and rerun the matrix.
5. Validate acceptance rule plus NFR budgets, then document commands, profile
   identity, and final metrics.

## Risks

- overfitting BTC while degrading ETH
- improving totals while worsening bucket overlap
- regressing the default local profile if profile selection is not isolated
- tuning too much to CoinAnK visual quirks instead of stable liq-map semantics
- candidate churn without a clean fallback decision
- underestimating runtime/report-size budgets during repeated calibration loops

## Quickstart

Use the `spec-017` matrix and filter evaluation to CoinAnK-focused pairwise
metrics only. The implementation phase should add a single command path for
selecting `rektslug-ank`.
