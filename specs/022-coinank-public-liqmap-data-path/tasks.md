# Tasks: CoinAnK Public Liq-Map Data Path

**Input**: `specs/022-coinank-public-liqmap-data-path/spec.md`
**Dependencies**: `spec-017`, `spec-018`, `spec-020`
**Feature Type**: Backend/public-route rewrite

## Phase 1: Baseline Audit

- [ ] T001 Capture the current public-route mismatch for `BTC/ETH x 1d/1w` using the canonical `/chart/derivatives/liq-map/...` URLs
- [ ] T002 Document the current payload limitations of the public route versus CoinAnK (`grid`, `ladder`, `cdf`, `axes`)
- [ ] T003 [P] Decide and document whether the dedicated public path will be a new endpoint or an internal builder behind the existing route

## Phase 2: Contract and RED Tests

- [ ] T004 Write failing tests for the dedicated public builder contract
- [ ] T005 Write failing tests for symbol-aware and timeframe-aware grid generation (`BTC/ETH`, `1d/1w`)
- [ ] T006 Write failing tests that the public path preserves richer leverage-ladder detail before frontend grouping
- [ ] T007 Write failing tests that cumulative long/short anchor correctly at current price
- [ ] T008 Write failing tests that the canonical public HTML route consumes the dedicated public path, not the legacy compressed shape

## Phase 3: Backend Rewrite

- [ ] T009 Implement the dedicated CoinAnK-style public data builder
- [ ] T010 Implement symbol-aware and timeframe-aware price-grid generation
- [ ] T011 Implement public-route leverage ladder generation suitable for provider-like grouping
- [ ] T012 Implement cumulative series generation from the dedicated public dataset
- [ ] T013 Thread the dedicated public builder into `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}` without breaking the URL contract

## Phase 4: Validation

- [ ] T014 Run public-route validation for `BTCUSDT 1d`
- [ ] T015 Run public-route validation for `BTCUSDT 1w`
- [ ] T016 Run public-route validation for `ETHUSDT 1d`
- [ ] T017 Run public-route validation for `ETHUSDT 1w`
- [ ] T018 Confirm `1d` and `1w` public views are materially distinct and no longer collapse into near-identical output
- [ ] T019 Confirm the public route uses stale-real data rather than synthetic fallback whenever DuckDB-backed data is available

## Phase 5: Documentation

- [ ] T020 Document the new public-route backend contract and how it supersedes the remaining backend/data-path gap in `spec-016`
- [ ] T021 Record final validation artifacts and residual differences, if any
