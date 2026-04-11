# Feature Specification: Canonical Liq-Map Product Hardening

**Feature Branch**: `032-canonical-liqmap-product-hardening`
**Created**: 2026-04-10
**Status**: Implemented
**Dependencies**: spec-020 (visual harness), spec-022 (CoinAnK public liq-map data path), spec-030 (modeled snapshot contract), spec-031 (unified Binance/Bybit public serving)

## Context

`rektslug` now has a real canonical liquidation-map product:

- browser route: `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}`
- canonical frontend: `frontend/liq_map_1w.html`
- public API surfaces:
  - Binance / Bybit: `/liquidations/coinank-public-map`
  - Hyperliquid: `/liquidations/hl-public-map`

At the same time, the repository still contains a legitimate legacy liq-map surface:

- `/liquidations/levels`

That legacy surface is still useful for internal OI-model inspection and profile-based calibration, but it is not the same thing as the canonical product.

The repo is now in an awkward middle state:

- product-facing routes and validators increasingly assume the public surface
- some capture/comparison/calibration flows still assume the legacy surface
- downstream parsers now support both contracts, but the upstream workflow contract is still implicit
- Binance public serving still has a real internal fallback path that can switch from artifact-backed serving to the legacy builder without product-level provenance

This spec exists to harden the canonical liq-map product boundary before further model-calibration or provider-parity work.

## Goal

Freeze the canonical `liq-map` product surface and make workflow surface selection explicit, so product validation, capture, comparison, and calibration stop depending on ambiguous legacy/public assumptions.

## Scope

### In Scope

- Define a first-class workflow `surface` axis for liq-map: `public` vs `legacy`
- Freeze the canonical product route/API matrix for Binance, Bybit, and Hyperliquid
- Require product-facing workflows to default to the canonical public surface
- Require calibration/internal-model workflows to declare legacy usage explicitly
- Persist surface selection and effective endpoint provenance in manifests/reports
- Make Binance public fallback behavior explicit at the product/validation layer
- Tighten workflow invariants so exchange/timeframe/surface routing can be tested directly

### Out of Scope

- New provider-parity mathematics
- Implementing `model=coinank|coinglass` on the public builder
- Coinglass-style parity for the public liq-map
- Heatmap work (`spec-024`, `spec-025`, `/chart/derivatives/liq-heat-map/...`)
- Hyperliquid variant redesign
- Removal of legacy `/liquidations/levels` from the repo

## Problem Statement

The current product is good enough to use, but not yet hard enough to trust as a stable product boundary.

Today the repo still mixes two different ideas:

1. **Canonical product validation**
   - "Does the real public liq-map route behave correctly?"
2. **Internal model calibration**
   - "Does the older internal OI-model family behave as expected?"

Those are not the same workflow, but the repo still lets them blur together.

That ambiguity causes three concrete problems:

- capture/validation tools can silently validate the wrong surface
- manifests/reports do not always preserve which surface was actually validated
- Binance public serving can appear stable while hiding whether the response came from the artifact-backed path or the legacy fallback path

## Architectural Decision

This spec freezes the following product rules:

1. The canonical liq-map product remains the existing browser route:
   - `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}`
2. The repo will not invent a third liq-map surface.
3. Workflow tools will select between the two existing surfaces explicitly:
   - `public`
   - `legacy`
4. Product-facing workflows default to `public`.
5. Calibration/model-inspection workflows may keep using `legacy`, but only explicitly.
6. Product hardening and provider-parity/model work remain separate backlog tracks.

## Canonical Product Matrix

For the purposes of this spec, the canonical liq-map product is:

| Exchange | Canonical Browser Route | Canonical API Surface |
|----------|--------------------------|------------------------|
| Binance | `/chart/derivatives/liq-map/binance/{symbol}/{timeframe}` | `/liquidations/coinank-public-map` |
| Bybit | `/chart/derivatives/liq-map/bybit/{symbol}/{timeframe}` | `/liquidations/coinank-public-map` |
| Hyperliquid | `/chart/derivatives/liq-map/hyperliquid/{symbol}/{timeframe}` | `/liquidations/hl-public-map` |

The legacy surface remains:

- `/liquidations/levels`

but it is not the canonical product surface.

## Requirements

### Functional Requirements

- **FR-001**: Every liq-map workflow that captures, validates, compares, or scores local Rektslug data MUST expose an explicit `surface` concept with enum `{public, legacy}`.
- **FR-002**: For product-facing liq-map validation, the default `surface` MUST be `public`.
- **FR-003**: For Binance and Bybit, `surface=public` MUST resolve to `/liquidations/coinank-public-map`.
- **FR-004**: For Hyperliquid, `surface=public` MUST resolve to `/liquidations/hl-public-map`.
- **FR-005**: `surface=legacy` MUST resolve to `/liquidations/levels` only; tools MUST NOT silently remap `legacy` to a public endpoint.
- **FR-006**: Calibration/internal-model workflows that still depend on `/liquidations/levels` MUST declare `surface=legacy` explicitly in CLI, manifest, or report metadata.
- **FR-007**: Manifests/reports produced by liq-map workflows MUST record:
  - requested surface
  - effective surface
  - effective API endpoint path
  - exchange
  - symbol
  - timeframe
- **FR-008**: Workflow tools MUST NOT silently fall back across surfaces. If a requested surface cannot be reached by workflow logic, the run MUST fail explicitly.
- **FR-009**: Binance public-surface validation MUST distinguish between:
  - artifact-backed public serving
  - public route served via legacy fallback inside the backend
- **FR-010**: Comparison/gap-analysis/calibration loaders MUST remain capable of reading both public and legacy liq-map capture payloads from historical manifests.
- **FR-011**: Hyperliquid MUST remain public-only for the canonical product path in this spec; no workflow may treat `/liquidations/levels` as the canonical Hyperliquid product surface.

### Non-Functional Requirements

- **NFR-001**: This spec MUST harden the existing product without requiring a redesign of the canonical frontend route.
- **NFR-002**: Legacy workflows MUST remain runnable during migration, but their legacy status must become explicit.
- **NFR-003**: Product hardening under this spec MUST not be blocked on `model=coinank|coinglass` work from `spec-026`.
- **NFR-004**: The added surface/provenance semantics SHOULD be machine-readable and stable enough for automated validation/report tooling.

## Success Criteria

- A local liq-map validation run can no longer be ambiguous about whether it validated `public` or `legacy`.
- Product-facing validators and browser tests default to the canonical public surface.
- Calibration workflows still run, but their use of the legacy surface is explicit in artifacts/reports.
- Binance public runs explicitly reveal whether they were artifact-backed or served through legacy fallback.
- Bybit and Hyperliquid public routing remain covered by canonical-route tests without legacy assumptions leaking in.
