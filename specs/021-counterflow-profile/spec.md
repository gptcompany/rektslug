# Spec 021: Counterflow Profile

## Overview

Define how `bitcoincounterflow` fits into the comparison ecosystem as a distinct
provider/profile that uses TradingView Lightweight Charts for presentation.

This spec is not a copy of `spec-017`:

- Counterflow is primarily useful as a reference profile and capture target
- its UI technology differs from the current local Plotly path

## Reference Sources

- `docs/provider-api-comparison.md`
- `scripts/capture_provider_api.py`
- `scripts/compare_provider_liquidations.py`
- `scripts/run_provider_api_comparison.py`
- `specs/020-visual-comparison-harness/spec.md`
- `specs/020-visual-comparison-harness/plan.md`

## Scope

### In Scope

- inventory existing Counterflow routes and capture behavior
- define provider profile metadata for Counterflow
- establish how Counterflow participates in comparison and visual harness flows
- document renderer-specific constraints stemming from TradingView Lightweight

### Out of Scope

- replatforming the local chart renderer to TradingView
- full heatmap parity work
- CoinAnK/Coinglass profile calibration

## Reference URLs

- Counterflow page: `https://bitcoincounterflow.com/liquidation-heatmap/`
- Counterflow API: `https://api.bitcoincounterflow.com/api/liquidations`

## Tooling Assumptions

- Counterflow should be treated as a TradingView Lightweight Charts provider until proven otherwise by implementation-level validation.
- If a local Lightweight smoke page is needed later, it should be validated separately from the current Plotly pages rather than assumed interchangeable.

## Functional Requirements

- **FR-001**: The repo MUST define Counterflow as an explicit provider/profile, not an unnamed extra endpoint.
- **FR-002**: Counterflow participation in manifests/reports MUST be explicit and separable from CoinAnK and Coinglass.
- **FR-003**: The spec MUST document renderer constraints relevant to visual comparison against a Lightweight Charts provider.
- **FR-004**: Counterflow integration MUST be compatible with the shared visual harness from `spec-020`.

## Success Criteria

- **SC-001**: Counterflow has a clear role in the repo architecture and docs.
- **SC-002**: A future implementation can plug Counterflow into manifests/reports without ad-hoc one-off logic.
- **SC-003**: The renderer mismatch implications are documented before implementation begins.
