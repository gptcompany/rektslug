# Implementation Plan: Public Liq-Map Provider Parity

**Spec**: `specs/033-public-liqmap-provider-parity/spec.md`
**Feature Type**: Product-model hardening
**Branch**: master

## Summary

This plan turns the public `liq-map` route into a provider-parity workflow with
a measurable model axis. The key decision is to keep `surface=public` as the
product surface and add `reference_provider` as the provider-parity profile.

CoinAnK is the default product reference. Coinglass is a secondary diagnostic
profile because its per-exchange Binance map differs materially from CoinAnK in
scale and shape.

## Current State

- `spec-032` makes `surface=public|legacy` explicit.
- `/liquidations/coinank-public-map` serves Binance and Bybit public map
  payloads.
- Public responses now expose `serving_provenance`.
- The current public artifact bridge can serve modeled snapshots, but it does
  not yet preserve a proven provider-specific leverage ladder.
- Historical provider-comparison reports mostly compared legacy
  `/liquidations/levels`; spec 033 needs fresh `surface=public` baselines.

## Architecture

```
provider references
  CoinAnK getLiqMap
  Coinglass Binance per-exchange liqMap
        +
local Rektslug public map
  /liquidations/coinank-public-map?exchange=binance&symbol=...&timeframe=...
  workflow surface=public
        +
provider-normalized metrics
  scale, L/S ratio, grid, shape, peaks
        ->
versioned parity report
        ->
public builder profile tuning
  reference_provider=coinank
  reference_provider=coinglass
        ->
canonical public route remains unchanged
```

## Design Decisions

### D1: CoinAnK First

Binance/CoinAnK is the first signoff target because the current active scope is
Binance-first and the route is named and shaped around CoinAnK-style public map
serving.

### D2: No Blended Provider Model

CoinAnK and Coinglass disagree on scale and sometimes shape. The product should
not hide that behind a blended model. Provider parity must be explicit:

- `reference_provider=coinank`
- `reference_provider=coinglass`

### D3: Metadata Before Tuning

Before tuning the public builder, the workflow must emit enough metadata to
prove what was compared:

- requested/effective surface
- effective endpoint path
- serving provenance
- artifact model and timestamp
- reference provider
- calibration id/version

### D4: Display Fallback Is Not Evidence

Equal distribution across leverage tiers may remain as a display fallback, but
it cannot be used as evidence of provider ladder parity. Final signoff needs
either provider-shaped ladder data or explicit metadata that the ladder is
display-only and excluded from parity scoring.

### D5: Bybit And Hyperliquid Stay Guarded

Bybit public serving must keep passing regression tests, but Bybit provider
parity follows after Binance. Hyperliquid remains on `/liquidations/hl-public-map`
and is governed by spec-026 for its CoinGlass/top-position parity questions.

## Phase Plan

### Phase 1: Public Baseline Refresh

- Run the current comparison workflow with `surface=public`.
- Freeze the 4-entry Binance public baseline:
  - `BTCUSDT x 1d`
  - `BTCUSDT x 1w`
  - `ETHUSDT x 1d`
  - `ETHUSDT x 1w`
- Record `serving_provenance` and treat `legacy-fallback` as evidence only, not
  final artifact-backed signoff.

### Phase 2: Metrics And Report Contract

- Add a provider-parity report schema.
- Implement or extend report generation to compute:
  - total scale ratio
  - long/short ratio delta
  - bucket count ratio
  - price step ratio
  - normalized overlap
  - normalized Wasserstein distance
  - Pearson correlation
  - top peak hit rate
- Store reports separately from generic provider-comparison JSON when useful,
  under a path such as:
  - `data/validation/public_liqmap_provider_parity/`

### Phase 3: Public API Profile Axis

- Add `reference_provider` to the public map API.
- Add response metadata:
  - `reference_provider`
  - `parity_model_id`
  - `parity_model_version`
  - `parity_calibration_id`
- Preserve default behavior when the parameter is omitted:
  - default `reference_provider=coinank`

### Phase 4: CoinAnK Profile Tuning

- Make CoinAnK-specific grid, L/S ratio, scale, and peak alignment explicit
  calibration targets.
- Replace or label equal leverage spreading so it cannot masquerade as true
  provider ladder parity.
- Version calibration coefficients by source run and matrix entry.
- Gate the result on the initial CoinAnK parity score:
  - every matrix entry `>= 70`
  - matrix average `>= 80`

### Phase 5: Coinglass Diagnostic Profile

- Keep Coinglass as secondary.
- Use only Binance per-exchange `liqMap`, not aggregate or heatmap endpoints.
- Emit diagnostic scores and failure reasons.
- Do not change the default public product based on Coinglass until a separate
  signoff decision is made.

### Phase 6: Documentation And Handoff

- Update current docs to state:
  - CoinAnK is the default public reference profile
  - Coinglass is explicit and secondary
  - heatmap is out of scope
  - no provider is treated as ground truth
- Produce a final handoff with:
  - accepted calibration id
  - report paths
  - test commands
  - remaining follow-up for Bybit/provider variants

## Test Strategy

- Unit tests for `reference_provider` parsing and validation.
- Contract tests for new public response metadata.
- Report tests for parity metrics and score computation.
- Regression tests proving omitted `reference_provider` still defaults to
  CoinAnK.
- Browser tests proving canonical public routes still resolve correctly for
  Binance, Bybit, and Hyperliquid.
- Workflow tests proving `surface=public` is used for public provider-parity
  runs and legacy reports remain readable.

## Risks

- Provider drift changes reference values between capture and calibration.
- CoinGlass decode breaks due bundle/header changes.
- Tuning to one capture overfits to a transient market snapshot.
- Scale improves while shape gets worse.
- Bybit public route regresses while Binance tuning is underway.
- Display-only leverage expansion is mistaken for real provider ladder parity.

## First Implementation Slice

The first slice should be:

1. Add RED tests and implementation for a small provider-parity metrics module.
2. Add `reference_provider` metadata to public API response contracts with
   default `coinank`.
3. Extend the comparison workflow or create a focused report wrapper that runs
   `surface=public` and emits the new metric contract.
4. Generate the public Binance baseline before changing model math.
