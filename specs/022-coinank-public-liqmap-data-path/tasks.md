# Tasks: CoinAnK Public Liq-Map Data Path

**Input**: `specs/022-coinank-public-liqmap-data-path/spec.md`
**Dependencies**: `spec-017`, `spec-018`, `spec-020`
**Feature Type**: Backend/public-route rewrite

## Phase 1: Baseline Audit

- [ ] T001 Capture the current public-route mismatch for `BTC/ETH x 1d/1w` using the canonical `/chart/derivatives/liq-map/...` URLs
- [ ] T002 Document the current payload limitations of the public route versus CoinAnK (`grid`, `ladder`, `cdf`, `axes`)
- [ ] T003 Freeze the implementation decision and contract: new endpoint `GET /liquidations/coinank-public-map` backed by an internal builder, with legacy `/liquidations/levels` preserved

## Phase 2: Contract and RED Tests

- [ ] T004 Write failing tests for the typed public builder contract / response schema
- [ ] T005 Write failing tests for symbol-aware and timeframe-aware grid generation (`BTC/ETH`, `1d/1w`), including unsupported symbol/timeframe rejection
- [ ] T006 Write failing tests that the public path preserves richer leverage-ladder detail before frontend grouping
- [ ] T007 Write failing tests that cumulative long/short anchor correctly at current price
- [ ] T008 Write failing tests that the canonical public HTML route consumes `/liquidations/coinank-public-map`, not legacy `/liquidations/levels`
- [ ] T008a Write failing regression tests that legacy `/liquidations/levels` behavior remains available for existing workflows
- [ ] T008b Write failing tests for explicit builder failure behavior: HTTP 500 with JSON `{"error", "detail"}`, no partial HTML chart or silent legacy fallback
- [ ] T008c Write failing E2E test (Playwright) that `frontend/liq_map_1w.html` renders correctly from the new endpoint payload
- [ ] T008d Write failing tests that BTC and ETH use different grid steps and that `1d` and `1w` use different range envelopes

## Phase 3: Backend Rewrite

- [ ] T009 Implement the dedicated CoinAnK-style public data builder
- [ ] T010 Implement symbol-aware and timeframe-aware price-grid generation using the frozen step/snap rules from the spec
- [ ] T011 Implement public-route leverage ladder generation suitable for provider-like grouping
- [ ] T012 Implement cumulative series generation from the dedicated public dataset
- [ ] T013 Expose the builder via `GET /liquidations/coinank-public-map`
- [ ] T014 Update `frontend/liq_map_1w.html` to consume the new endpoint on canonical public CoinAnK-style routes while preserving the existing HTML URL contract
- [ ] T015 Keep legacy `/liquidations/levels` regression-green for existing non-public workflows; update or remove the stale `Sunset: 2025-06-01` header

## Phase 3b: Refactor

- [ ] T015b Refactor the public liqmap builder after GREEN tests pass: clean up internal helpers, remove duplication, verify all tests still green

## Phase 4: Validation

- [ ] T016 Run public-route validation for `BTCUSDT 1d`
- [ ] T017 Run public-route validation for `BTCUSDT 1w`
- [ ] T018 Run public-route validation for `ETHUSDT 1d`
- [ ] T019 Run public-route validation for `ETHUSDT 1w`
- [ ] T020 Confirm `1d` and `1w` public views are materially distinct and no longer collapse into near-identical output
- [ ] T021 Confirm the public route uses stale-real data rather than synthetic fallback whenever DuckDB-backed data is available
- [ ] T022 Measure the first structural pass gates: builder response `< 2s` warm / `< 10s` cold, validation runtime `< 120s`, manifest+score `< 1 MB`, and visual score `>= 90`
- [ ] T022b Verify rollback path: confirm the frontend can revert to legacy `/liquidations/levels` by removing the endpoint switch, and that the legacy path still renders a valid chart

## Phase 5: Documentation

- [ ] T023 Document the new public-route backend contract and how it supersedes the remaining backend/data-path gap in `spec-016`
- [ ] T024 Record final validation artifacts and residual differences, if any
