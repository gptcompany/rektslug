# Plan: Canonical Liq-Map Product Hardening (spec-032)

## Phase 1: Scope Freeze

1. **Freeze Product Boundary**
   - canonical browser route remains `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}`
   - canonical API surfaces remain the existing public endpoints
   - legacy `/liquidations/levels` remains available but non-canonical
2. **Freeze Separation of Concerns**
   - this spec hardens the product/workflow contract
   - provider-parity math stays outside this spec
   - heatmap work stays outside this spec

## Phase 2: Workflow Surface Contract

1. **Introduce First-Class Surface Selection**
   - add `surface=public|legacy` to local liq-map workflow entrypoints
   - ensure default is `public` for product-facing tooling
2. **Define Workflow Defaults**
   - `scripts/validate_liqmap_visual.py` -> `public`
   - visual harness local liq-map capture -> `public`
   - product-facing provider comparison runs -> `public`
   - calibration flows (`run_ank_calibration.py`, `run_glass_calibration.py`) -> explicit `legacy`
3. **Route Matrix**
   - Binance / Bybit public -> `/liquidations/coinank-public-map`
   - Hyperliquid public -> `/liquidations/hl-public-map`
   - legacy -> `/liquidations/levels`

## Phase 3: Manifest and Report Semantics

1. **Persist Requested vs Effective Surface**
   - requested surface
   - effective surface
   - endpoint path / source URL
2. **Propagate Surface Through Comparison Layers**
   - capture manifests
   - normalized datasets
   - gap-analysis state
   - calibration reports
3. **Avoid Silent Reinterpretation**
   - reports must not infer surface only from ad hoc substring checks

## Phase 4: Binance Public Fallback Provenance

1. **Freeze Binance Policy**
   - decide whether public serving may still use backend legacy fallback
   - if yes, expose that provenance explicitly
   - if no, fail public runs explicitly when artifact-backed serving is unavailable
2. **Surface Provenance**
   - artifact-backed public response
   - public route backed by legacy fallback
   - Hyperliquid dedicated public builder

## Phase 5: Validation

1. **CLI / Workflow Validation**
   - explicit surface selection works for product and calibration tools
2. **Manifest Validation**
   - surface metadata survives through manifests/reports
3. **Canonical Route Validation**
   - Binance public route
   - Bybit public route
   - Hyperliquid public route
4. **Regression Validation**
   - legacy calibration workflows remain runnable
   - legacy payload readers still work on historical artifacts
