# Implementation Plan: Counterflow Profile

**Spec**: `specs/021-counterflow-profile/spec.md`
**Feature Type**: Provider profile / planning
**Branch**: master

## Summary

Clarify how Counterflow should be represented and compared in the repo before
any implementation mixes TradingView Lightweight-specific behavior into the
existing Plotly-oriented workflows.

## Technical Context

### Existing Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| `scripts/capture_provider_api.py` | Exists | Counterflow already appears in provider choices |
| `scripts/compare_provider_liquidations.py` | Exists | Counterflow parser exists for raw liquidation feed |
| `scripts/run_provider_api_comparison.py` | Exists | Counterflow still available outside locked `spec-017` runs |
| local renderer | Plotly | Different from Counterflow's Lightweight renderer |
| future visual harness | Planned | `spec-020` should provide the integration seam |

### Source Documents

- `docs/provider-api-comparison.md`
- `specs/020-visual-comparison-harness/spec.md`
- `specs/020-visual-comparison-harness/plan.md`

### Reference URLs

- Counterflow page: `https://bitcoincounterflow.com/liquidation-heatmap/`
- Counterflow API: `https://api.bitcoincounterflow.com/api/liquidations`

### TradingView Lightweight Decision

The repo does not currently ship a local Lightweight Charts implementation or a
JS build system for it. For this reason:

- do not add a root-level install as part of planning only
- first validate the provider role, renderer constraints, and harness adapter seam
- if implementation requires a local smoke page, prefer a minimal isolated adapter
  with explicit installation and validation steps rather than implicit repo-wide adoption

### Validation Prerequisite if Lightweight Is Introduced Later

If a future implementation adds TradingView Lightweight Charts locally, the
first acceptance gate should be a minimal smoke page that confirms:

- library loads without a separate app build requirement
- a trivial candlestick/overlay renders locally
- screenshot capture works under Playwright/Chromium
- the resulting DOM/canvas output is stable enough for the `spec-020` harness

### Harness Integration Rule

Counterflow should integrate into `spec-020` under:

- `product_adapter`: chosen separately by the consuming workflow
- `renderer_adapter=lightweight`

This avoids confusing renderer decisions with dataset/product decisions.

## Architecture

```
Counterflow provider identity
        +
manifest/report metadata
        +
visual harness adapter
        ->
future comparison runs
```

## What Already Works

- Counterflow can already be captured by the provider API workflow
- raw `/api/liquidations` payloads already have a parser
- provider choice already exists in orchestration scripts
- shared provider-profile metadata can now expose Counterflow explicitly in normalized reports

## What Needs Work

1. explicit definition of Counterflow's architectural role
2. separation between data-source and visual-reference semantics
3. adapter design for the shared visual harness
4. an explicit future decision on whether local Lightweight smoke validation is worth adding

## Current Implementation Decision

Counterflow should now be represented with explicit provider-profile metadata:

- provider key: `bitcoincounterflow`
- display name: `Bitcoin CounterFlow`
- roles: `data-source`, `visual-reference`
- default renderer adapter: `lightweight`

This metadata belongs beside manifests/reports, not inside normalized dataset
shape fields.

## Harness Alignment

When Counterflow enters the shared visual harness, it should do so through:

- `provider = bitcoincounterflow`
- `renderer_adapter = lightweight`
- a product adapter chosen by the consuming workflow

Counterflow must not become:

- a special-case global runner branch
- a hidden URL-only provider identity
- a replacement for product-adapter selection

## Future Smoke Run

If a later implementation needs live Lightweight validation, the first smoke
run should be intentionally narrow:

```bash
uv run python scripts/run_visual_harness.py \
  --provider bitcoincounterflow \
  --renderer lightweight \
  --product liq-heat-map \
  --window 48h
```

That command is a contract target, not a claim that the live provider adapter
exists today.

Current decision:

- no local Lightweight smoke page is needed yet
- no repo-wide Lightweight install should happen for planning only
- if a future spec introduces it, installation and Playwright validation must be
  documented as a dedicated gate first

## Phases

1. Inventory routes and current repo touchpoints.
2. Define Counterflow's architectural role.
3. Align with `spec-020` so later implementation is clean.

## Risks

- treating Counterflow as equivalent to CoinAnK/Coinglass when it serves a different role
- ignoring renderer differences until too late
- reusing comparison logic that assumes Plotly-like behavior
- installing Lightweight Charts prematurely without first proving the adapter path
