# Tasks: spec-033 Public Liq-Map Provider Parity

## Phase 1: Scope And Baseline

- [ ] T001 Freeze `reference_provider` as the public-route provider-parity profile axis with enum `{coinank, coinglass}`
- [ ] T002 Freeze CoinAnK as the default public reference profile and Coinglass as secondary diagnostic profile
- [ ] T003 Explicitly mark heatmap, Hyperliquid top-position parity, and Bybit signoff out of scope for the first Binance parity pass
- [ ] T004R RED: Write tests proving provider-parity baseline workflows use `surface=public`, not `/liquidations/levels`
- [ ] T005 Generate or document a fresh public Binance baseline for `BTC/ETH x 1d/1w`
- [ ] T006 Persist baseline serving provenance and mark `legacy-fallback` runs as evidence-only, not final artifact-backed signoff

## Phase 2: Parity Metrics Contract

- [ ] T007R RED: Write tests for provider-parity metric computation on two small synthetic price-bin datasets
- [ ] T008 Implement metric helpers for total scale ratio, long/short ratio delta, bucket count ratio, and price step ratio
- [ ] T009 Implement normalized shape metrics: overlap coefficient, normalized Wasserstein distance, and Pearson correlation
- [ ] T010 Implement top-peak hit-rate metric with grid-step tolerance
- [ ] T011 Implement the initial CoinAnK `parity_score` weighting contract
- [ ] T012 Add tests for score failure when scale improves but normalized shape regresses materially
- [ ] T013 Keep historical provider-comparison report loading backward compatible when parity fields are absent

## Phase 3: Public API Profile Metadata

- [ ] T014R RED: Write public API contract tests for default `reference_provider=coinank`
- [ ] T015R RED: Write public API contract tests rejecting unsupported `reference_provider` values
- [ ] T016 Add `reference_provider` request parsing to `/liquidations/coinank-public-map`
- [ ] T017 Add public response metadata: `reference_provider`, `parity_model_id`, `parity_model_version`, `parity_calibration_id`
- [ ] T018 Ensure `serving_provenance` remains distinct from `reference_provider` in response and validator metadata
- [ ] T019 Update validator preflight/manifest reporting to include provider-parity metadata

## Phase 4: Public Comparison Workflow

- [ ] T020R RED: Write workflow tests for a focused public provider-parity report artifact
- [ ] T021 Add a focused report wrapper or extend the comparison workflow to emit the spec-033 metric contract
- [ ] T022 Store public provider-parity reports under a deterministic output path
- [ ] T023 Ensure report artifacts include provider capture ids, local endpoint path, surface, serving provenance, and reference provider
- [ ] T024 Add CLI examples for CoinAnK and Coinglass profile runs

## Phase 5: CoinAnK Profile Tuning

- [ ] T025R RED: Write tests that equal-volume leverage spreading is labeled as display-only and cannot satisfy final parity signoff
- [ ] T026 Make CoinAnK price grid and effective step explicit model inputs for `BTC/ETH x 1d/1w`
- [ ] T027 Make CoinAnK long/short ratio a first-class calibration target
- [ ] T028 Add versioned calibration coefficients with source run ids
- [ ] T029 Tune the CoinAnK profile against the fresh public baseline
- [ ] T030 Verify CoinAnK gate: every matrix entry `parity_score >= 70`, matrix average `>= 80`

## Phase 6: Coinglass Diagnostic Profile

- [ ] T031R RED: Write tests proving Coinglass profile uses Binance per-exchange `liqMap`, not aggregate or heatmap endpoints
- [ ] T032 Add Coinglass diagnostic profile metadata and report generation
- [ ] T033 Ensure Coinglass decode/provider failure is explicit and does not block CoinAnK product signoff
- [ ] T034 Produce a Coinglass diagnostic report for the same `BTC/ETH x 1d/1w` matrix, if provider capture is available

## Phase 7: Regression And Documentation

- [ ] T035 Keep browser-route regression coverage green for Binance, Bybit, and Hyperliquid public flows
- [ ] T036 Keep API regression coverage green for Bybit artifact-backed serving
- [ ] T037 Update `CURRENT_SCOPE.md` and provider-comparison docs with the spec-033 provider-parity decision
- [ ] T038 Produce final handoff with accepted calibration id, report paths, tests run, and remaining follow-up
- [ ] T039 Run targeted test suite for API contracts, metrics, workflow reports, and browser-route regressions
