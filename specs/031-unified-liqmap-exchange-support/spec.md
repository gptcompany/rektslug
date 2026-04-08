# Feature Specification: Unified Public Liq-Map Serving (Binance & Bybit)

**Feature Branch**: `031-unified-liqmap-exchange-support`
**Created**: 2026-04-08
**Status**: Draft
**Dependencies**: spec-016 (CoinAnK-style Binance parity), spec-022 (public liq-map data path), spec-030 (Binance/Bybit modeled snapshot contract)

## Context

`rektslug` already has a mature public CoinAnK-style liquidation map flow for Binance through `/liquidations/coinank-public-map`.

`spec-030` introduced deterministic modeled snapshot artifacts for Binance and Bybit. That creates a natural next step:

- keep `spec-030` focused on producer/file-contract responsibilities
- add a separate serving-layer spec that consumes those artifacts for the public API and frontend

Bybit belongs in that serving layer. Hyperliquid does not, at least not yet:

- Bybit now has `spec-030` artifacts that can be adapted into the public builder contract
- Hyperliquid still has different producer semantics, variant handling, and a dedicated public endpoint (`/liquidations/hl-public-map`)

This spec exists to formalize the serving-layer work without retroactively expanding `spec-030` scope.

## Goal

Serve Binance and Bybit through the same public CoinAnK-style API and frontend path, using `spec-030` artifacts where available, while keeping Hyperliquid explicitly outside this spec.

## Scope

### In Scope

- Extend `/liquidations/coinank-public-map` with an `exchange` parameter for `binance` and `bybit`
- Add `exchange` to the public response contract
- Adapt `binance_standard` and `bybit_standard` artifacts from `spec-030` into `CoinankPublicMapResponse`
- Route Bybit CoinAnK-style frontend views through the same public endpoint as Binance
- Preserve the existing Binance fallback path if an artifact is unavailable

### Out of Scope

- Unifying Hyperliquid under `/liquidations/coinank-public-map`
- Replacing `/liquidations/hl-public-map`
- Changing `spec-030` producer responsibilities beyond compatibility fixes needed for artifact consumption
- Defining timeframe-addressable artifact families beyond the current `snapshot_ts` model in `spec-030`

## Requirements

### Functional Requirements

- **FR-001**: `/liquidations/coinank-public-map` MUST accept `exchange` with enum `{binance, bybit}` under this spec.
- **FR-002**: `CoinankPublicMapResponse` MUST include an `exchange` field that identifies the effective source exchange.
- **FR-003**: For `exchange=bybit`, the public builder MUST consume `spec-030` artifacts and MUST NOT silently fall back to fake or empty output.
- **FR-004**: For `exchange=binance`, the public builder SHOULD prefer `spec-030` artifacts and MAY fall back to the legacy Binance public builder if an artifact is unavailable.
- **FR-005**: `frontend/liq_map_1w.html` MUST pass `exchange` when rendering Binance or Bybit CoinAnK-style routes.
- **FR-006**: Hyperliquid MUST remain on its dedicated endpoint and variant flow; it is explicitly outside this spec.
- **FR-007**: The public API MUST preserve the existing `timeframe` query contract (`1d`, `1w`). When the response is artifact-backed, `timeframe` MAY remain a serving/presentation concern until producer artifacts become timeframe-addressable.

### Non-Functional Requirements

- **NFR-001**: Artifact-backed responses SHOULD complete in under 500ms for local file reads and small response transforms.
- **NFR-002**: Backward compatibility for Binance public routes and legacy `/liquidations/levels` consumers MUST be preserved.
- **NFR-003**: This spec MUST remain a serving-layer spec. Producer/export contract changes remain governed by `spec-030`.

## Success Criteria

- `GET /liquidations/coinank-public-map?exchange=bybit&symbol=BTCUSDT&timeframe=1w` returns a valid public payload
- `/chart/derivatives/liq-map/bybit/btcusdt/1w` renders through the same public builder family used by Binance
- Binance public routes continue to work without regression
- Hyperliquid routes continue to use `/liquidations/hl-public-map` unchanged
