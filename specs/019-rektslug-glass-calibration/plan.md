# Implementation Plan: Rektslug-Glass Calibration

**Spec**: `specs/019-rektslug-glass-calibration/spec.md`
**Feature Type**: Local model calibration
**Branch**: master

## Summary

Reuse the `spec-017` liq-map comparison harness to create a Coinglass-specific
local profile. The goal is not generic parity but a clean, explicit
`rektslug-glass` profile.

## Technical Context

### Existing Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| `spec-017` reports | Exists | Already include Coinglass vs local pairwise metrics |
| `scripts/run_provider_api_comparison.py` | Exists | Full orchestrator for re-runs |
| `scripts/capture_provider_api.py` | Exists | REST/browser Coinglass capture |
| `scripts/compare_provider_liquidations.py` | Exists | Already normalizes Coinglass liq-map payloads |
| `scripts/coinglass_decode_payload.js` | Exists | Decoder support for encrypted responses |
| `scripts/coinglass_bundle_report.py` | Exists | Bundle drift monitoring |
| local model | Exists | Needs profile selection, not replacement |

### Source Documents

- `docs/provider-api-comparison.md`
- `docs/provider-api-handoff.md`
- `docs/runbooks/chart-routes.md`
- `specs/017-liqmap-provider-comparison/spec.md`
- `specs/017-liqmap-provider-comparison/plan.md`

### Required Environment Variables

- `COINGLASS_USER_LOGIN`
- `COINGLASS_USER_PASSWORD`
- `COINGLASS_APP_BUNDLE` (optional but useful)

### Reference URLs

- Coinglass page: `https://www.coinglass.com/pro/futures/LiquidationMap`
- Coinglass API: `https://capi.coinglass.com/api/index/5/liqMap`
- local liq-map matrix: see `docs/runbooks/chart-routes.md`

### Required Tools

- `uv run python ...`
- `dotenvx run -f /media/sam/1TB/.env -- ...`
- REST-first Coinglass capture, browser fallback only where needed

## Architecture

```
frozen spec-017 Coinglass references
        +
fresh local baseline captures (rektslug-default)
        ->
profile parameter experiments
        ->
rektslug-glass
        ->
full matrix rerun against Coinglass
```

## What Already Works

- deterministic Coinglass capture via REST or browser fallback
- liqMap decoding and normalization
- baseline reports that already expose current gap metrics

## What Needs Work

1. explicit local profile surface for Coinglass-oriented tuning
2. acceptance thresholds for provider-specific parity
3. protection against bundle drift during calibration
4. profile-isolation tests
5. fresh local baseline capture against frozen provider references

## Phases

1. Baseline audit and metric selection.
2. Profile-surface plumbing.
3. Parameter experiments per matrix entry.
4. Freeze one profile and rerun the matrix.
5. Document repeatable commands and results.

## Acceptance Notes

- Keep the global calibration rule aligned with `spec-018`: `3/5` metrics on `3/4` entries, no critical regression.
- Use a Coinglass-specific `bucket_overlap` improvement threshold of `>= 5%`.
- Compare both `rektslug-default` and `rektslug-glass` against the same frozen Coinglass reference per entry.

## Risks

- chasing Coinglass-specific clustering quirks too aggressively
- regressing other local profiles if configuration boundaries are weak
- treating structural parity as sufficient when totals/peaks are still far off
- bundle drift invalidating assumptions during the calibration window
