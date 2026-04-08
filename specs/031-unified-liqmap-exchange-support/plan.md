# Plan: Unified Public Liq-Map Serving (spec-031)

## Phase 1: Scope Freeze

1. **Freeze Boundary vs spec-030**
   - `spec-030` remains producer/export contract only
   - `spec-031` owns serving-layer API/frontend behavior only
2. **Freeze Supported Exchanges**
   - `binance`
   - `bybit`
   - Hyperliquid explicitly excluded from this spec

## Phase 2: Backend Serving Contract

1. **Public Response Contract**
   - Add `exchange` to `CoinankPublicMapResponse`
   - Keep the rest of the public builder schema compatible with existing consumers
2. **Route Contract**
   - Add `exchange` query parameter to `/liquidations/coinank-public-map`
   - Validate supported exchanges at the router
3. **Artifact Adapter**
   - Read `binance_standard` and `bybit_standard` artifacts from `spec-030`
   - Transform them into `CoinankPublicMapResponse`
   - Preserve Binance legacy fallback behavior

## Phase 3: Frontend Routing

1. **Binance and Bybit CoinAnK Paths**
   - Route both through `/liquidations/coinank-public-map`
   - Pass `exchange`, `symbol`, and `timeframe`
2. **Hyperliquid**
   - Keep `/liquidations/hl-public-map`
   - Do not fold variant logic into this spec

## Phase 4: Validation

1. **API Validation**
   - Bybit public payload returns valid data
   - Binance public payload does not regress
2. **Reader Semantics**
   - Ensure artifact lookup chooses a compatible available artifact
   - Avoid coupling public serving to a single newest manifest if that manifest is unusable
3. **Visual Validation**
   - Smoke-check Binance and Bybit CoinAnK-style routes
