# Tasks: ETH Production Validation

**Input**: `specs/023-eth-production-validation/spec.md`
**Dependencies**: spec-022 (public builder), spec-017 (comparison workflow)
**Feature Type**: Validation (no new production code)

## Phase 1: Structural Validation

- [ ] T001 [P] Call `/liquidations/coinank-public-map?symbol=ETHUSDT&timeframe=1d` and assert response schema matches CoinankPublicMapResponse
- [ ] T002 [P] Call `/liquidations/coinank-public-map?symbol=ETHUSDT&timeframe=1w` and assert response schema matches CoinankPublicMapResponse
- [ ] T003 Assert ETH 1d grid step is 0.5 and ETH 1w grid step is 2.0
- [ ] T004 Assert ETH bucket counts >= 15 long + 15 short for both timeframes
- [ ] T005 Assert ETH cumulative curves are monotonic and reach grid boundaries
- [ ] T006 Assert ETH 1d range envelope is distinct from 1w (narrower range)
- [ ] T007 Assert `is_stale_real_data=false` (data freshness gate)

**Checkpoint**: ETH builder output is structurally correct.

## Phase 2: Provider Comparison Baselines

- [ ] T008 Run gap-fill to ensure ETH data is fresh before comparison
- [ ] T009 [P] Run provider comparison for ETH 1D (`scripts/run_provider_api_comparison.py`)
- [ ] T010 [P] Run provider comparison for ETH 1W (`scripts/run_provider_api_comparison.py`)
- [ ] T011 Verify manifests contain all 3 providers (rektslug, coinank, coinglass)
- [ ] T012 Archive baselines under `data/validation/`

**Checkpoint**: ETH comparison baselines are reproducible.

## Phase 3: Visual Validation

- [ ] T013 Capture local ETH 1D screenshot via `/chart/derivatives/liq-map/binance/ETHUSDT/1d`
- [ ] T014 Capture local ETH 1W screenshot via `/chart/derivatives/liq-map/binance/ETHUSDT/1w`
- [ ] T015 [P] Capture CoinAnK ETH 1D reference screenshot
- [ ] T016 [P] Capture CoinAnK ETH 1W reference screenshot
- [ ] T017 Compare local vs CoinAnK screenshots — target >= 90 visual similarity

**Checkpoint**: ETH routes are visually validated against CoinAnK.

## Phase 4: Documentation & Regression

- [ ] T018 Write `specs/023-eth-production-validation/validation-results.md`
- [ ] T019 Re-run BTC 1d/1w structural assertions to confirm no regression
- [ ] T020 Mark spec-023 complete

## Dependencies

```
Phase 1 (structural)
  └─→ Phase 2 (comparison) ─── requires fresh data from T008
        └─→ Phase 3 (visual) ── requires running API + browser
              └─→ Phase 4 (docs)
```

T001-T002 parallel, T009-T010 parallel, T015-T016 parallel.

## MVP Strategy

1. Phase 1 can run offline with TestClient (no live API needed)
2. Phase 2-3 require live API + CoinAnK credentials
3. If CoinAnK login fails, Phase 3 is deferred but Phase 1-2 still valid
