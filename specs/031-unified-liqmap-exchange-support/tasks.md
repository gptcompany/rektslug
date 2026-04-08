# Tasks: spec-031 Unified Public Liq-Map Serving

## Phase 1: Scope Freeze

- [x] T001 Separate `spec-031` from `spec-030` as a serving-layer spec
- [x] T002 Narrow supported exchanges for this spec to `binance` and `bybit`
- [x] T003 Mark Hyperliquid as out of scope for the unified public endpoint

## Phase 2: Backend Serving Contract

- [x] T004 Add `exchange` to `CoinankPublicMapResponse`
- [x] T005 Add `exchange` query handling to `/liquidations/coinank-public-map`
- [x] T006 Validate supported exchanges in the router
- [x] T007 Add artifact-backed public response building for `binance_standard` and `bybit_standard`
- [x] T008 Preserve Binance legacy fallback behavior
- [x] T009 Return a real failure for missing Bybit artifacts instead of fake data
- [x] T010 Tighten reader semantics to pick the latest compatible available artifact, not just the latest manifest

## Phase 3: Frontend Routing

- [x] T011 Pass `exchange` to the unified public endpoint for Binance and Bybit CoinAnK-style routes
- [x] T012 Keep Hyperliquid on `/liquidations/hl-public-map`
- [x] T013 Keep public route behavior compatible with existing Binance views

## Phase 4: Validation and Handoff

- [x] T014 Keep integration coverage for the Bybit public route
- [x] T015 Smoke-check Binance and Bybit public payloads
- [x] T016 Document current timeframe semantics for artifact-backed responses
- [x] T017 Produce final handoff once T010 and T016 are closed
