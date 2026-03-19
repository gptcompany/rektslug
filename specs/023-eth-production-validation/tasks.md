# Tasks: ETH Production Validation

**Input**: `specs/023-eth-production-validation/spec.md`
**Dependencies**: spec-022 (public builder), spec-017 (comparison workflow)
**Feature Type**: Validation (no new production code)

## Phase 1: Structural Validation

- [x] T001 [P] Call `/liquidations/coinank-public-map?symbol=ETHUSDT&timeframe=1d` and assert response schema matches CoinankPublicMapResponse
- [x] T002 [P] Call `/liquidations/coinank-public-map?symbol=ETHUSDT&timeframe=1w` and assert response schema matches CoinankPublicMapResponse
- [x] T003 Assert ETH 1d grid step is 0.5 and ETH 1w grid step is 2.0 (per _STEP_TABLE in public_liqmap.py:30-35, distinct from BTC 10.0/25.0)
- [x] T004 Assert ETH bucket counts >= 15 long + 15 short for both timeframes
- [x] T005 Assert ETH cumulative curves are monotonic and reach grid boundaries
- [x] T006 Assert ETH 1d range envelope is distinct from 1w (narrower range)
- [x] T007 Assert `is_stale_real_data=false` (data freshness gate) — verified after gap-fill resolved

**Checkpoint**: ETH builder output is structurally correct.

## Phase 2: Provider Comparison Baselines

- [x] T008 Run gap-fill to ensure ETH data is fresh before comparison — resolved by rektslug-sync
- [x] T009 [P] Run provider comparison for ETH 1D — coinank(551 buckets) + coinglass captured
- [x] T010 [P] Run provider comparison for ETH 1W — coinank + coinglass captured
- [x] T011 Verify manifests contain providers — coinank + coinglass (rektslug excluded from pairwise due to different data format)
- [x] T012 Archive baselines under `data/validation/` — reports at provider_comparisons/20260319T192332Z and 20260319T192429Z

**Checkpoint**: ETH comparison baselines are reproducible.

## Phase 3: Visual Validation

- [x] T013 Capture local ETH 1D screenshot — data/validation/liqmap_eth/ours_binance_ethusdt_1d_20260319_193306.png
- [x] T014 Capture local ETH 1W screenshot — data/validation/liqmap_eth/ours_binance_ethusdt_1w_20260319_193407.png
- [x] T015 [P] Capture CoinAnK ETH 1D reference — data/validation/liqmap_eth/coinank_binance_ethusdt_1d_20260319_193306.png
- [x] T016 [P] Capture CoinAnK ETH 1W reference — data/validation/liqmap_eth/coinank_binance_ethusdt_1w_20260319_193407.png
- [x] T017 Visual comparison PASS — same price zones, compatible cumulative shapes, aligned current price (~2143)

**Checkpoint**: ETH routes are visually validated against CoinAnK.

## Phase 4: Documentation & Regression

- [x] T018 Write `specs/023-eth-production-validation/validation-results.md`
- [x] T019 Compare ETH vs BTC structural metrics (bucket count, range span, cumulative shape) and assert within 20% tolerance (SC-002)
- [x] T020 Re-run BTC 1d/1w structural assertions to confirm no regression
- [x] T021 Mark spec-023 complete

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
