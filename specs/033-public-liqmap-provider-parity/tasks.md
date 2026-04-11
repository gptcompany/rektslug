# Tasks: spec-033 Public Liq-Map Provider Parity

## Phase 1: Scope And Baseline

- [x] T001 Freeze `reference_provider` as the public-route provider-parity profile axis with enum `{coinank, coinglass}`
- [x] T002 Freeze CoinAnK as the default public reference profile and Coinglass as secondary diagnostic profile
- [x] T003 Explicitly mark heatmap, Hyperliquid top-position parity, and Bybit signoff out of scope for the first Binance parity pass
- [x] T004R RED: Write tests proving provider-parity baseline workflows use `surface=public`, not `/liquidations/levels`
- [x] T005 Generate or document a fresh public Binance baseline for `BTC/ETH x 1d/1w`
- [x] T006 Persist baseline serving provenance and mark `legacy-fallback` runs as evidence-only, not final artifact-backed signoff

## Phase 2: Parity Metrics Contract

- [x] T007R RED: Write tests for provider-parity metric computation on two small synthetic price-bin datasets
- [x] T008 Implement metric helpers for total scale ratio, long/short ratio delta, bucket count ratio, and price step ratio using Decimal/fixed-precision math
- [x] T009 Implement normalized shape metrics: overlap coefficient, normalized Wasserstein distance, and Pearson correlation with zero-total and zero-variance boundary handling
- [x] T010 Implement top-peak hit-rate metric with grid-step tolerance and deterministic tie-breaking
- [x] T011 Implement the initial CoinAnK `parity_score` weighting contract
- [x] T012 Add tests for score failure when scale improves but normalized shape regresses materially
- [x] T013 Keep historical provider-comparison report loading backward compatible when parity fields are absent
- [x] T014 Add RED tests for Metric Math Contract boundary cases: empty dataset, zero provider total, zero-variance vector, NaN/Infinity rejection, and out-of-range bucket filtering
- [x] T015 Add deterministic replay test proving a fixed local/provider fixture emits identical metrics and parity score across repeated runs

## Phase 3: Public API Profile Metadata

- [x] T016R RED: Write public API contract tests for default `reference_provider=coinank`
- [x] T017R RED: Write public API contract tests rejecting unsupported `reference_provider` values
- [x] T018 Add `reference_provider` request parsing to `/liquidations/coinank-public-map`
- [x] T019 Add public response metadata: `reference_provider`, `parity_model_id`, `parity_model_version`, `parity_calibration_id`
- [x] T020 Ensure `serving_provenance` remains distinct from `reference_provider` in response and validator metadata
- [x] T021 Update validator preflight/manifest reporting to include provider-parity metadata

## Phase 4: Public Comparison Workflow

- [x] T022R RED: Write workflow tests for a focused public provider-parity report artifact
- [x] T023 Add a focused report wrapper or extend the comparison workflow to emit the spec-033 metric contract
- [x] T024 Store public provider-parity reports under a deterministic output path
- [x] T025 Ensure report artifacts include provider capture ids, local endpoint path, surface, serving provenance, and reference provider
- [x] T026 Add CLI examples for CoinAnK and Coinglass profile runs

## Phase 5: CoinAnK Profile Tuning

- [x] T027R RED: Write tests that equal-volume leverage spreading is labeled as display-only and cannot satisfy final parity signoff
- [x] T028 Make CoinAnK price grid and effective step explicit model inputs for `BTC/ETH x 1d/1w`
- [x] T029 Make CoinAnK long/short ratio a first-class calibration target
- [x] T030 Define and validate the calibration artifact schema under `data/validation/public_liqmap_provider_parity/calibrations/{calibration_id}.json`
- [x] T031 Add versioned calibration coefficients with source run ids and rollback/audit metadata
- [x] T032 Tune the CoinAnK profile against the fresh public baseline
- [x] T033 Verify CoinAnK gate: every matrix entry `parity_score >= 70`, matrix average `>= 80`

## Phase 6: Coinglass Diagnostic Profile

- [x] T034R RED: Write tests proving Coinglass profile uses Binance per-exchange `liqMap`, not aggregate or heatmap endpoints
- [x] T035 Decide and test whether `reference_provider=coinglass` changes only metadata/reporting or also model coefficients in the public API
- [x] T036 Add Coinglass diagnostic profile metadata and report generation
- [x] T037 Ensure Coinglass decode/provider failure is explicit and does not block CoinAnK product signoff
- [x] T038 Produce a Coinglass diagnostic report for the same `BTC/ETH x 1d/1w` matrix, if provider capture is available

## Phase 7: Regression And Documentation

- [x] T039 Keep browser-route regression coverage green for Binance, Bybit, and Hyperliquid public flows
- [x] T040 Keep API regression coverage green for Bybit artifact-backed serving
- [x] T041 Add or record a performance validation for one public provider-parity report run completing in under 120s
- [x] T042 Add or record a warm public API response validation under 2s for one `(exchange, symbol, timeframe, reference_provider)` request
- [x] T043 Update `CURRENT_SCOPE.md` and provider-comparison docs with the spec-033 provider-parity decision
- [x] T044 Produce final handoff with accepted calibration id, report paths, tests run, and remaining follow-up
- [x] T045 Run targeted test suite for API contracts, metrics, workflow reports, browser-route regressions, and performance smoke checks

## Analysis Reconciliation

Issues addressed from the `speckit.analyze` round:

| Issue ID | Resolution |
|----------|------------|
| C1 | Added Metric Math Contract and boundary-test tasks for deterministic fixed-precision metric computation. |
| C2 | Added FR acceptance criteria table. |
| U1 | Added explicit parity score component formulas and Tier 1 failure behavior. |
| G1 | Added tasks for report runtime and warm API response performance validation. |
| I1 | Changed public API `reference_provider` wording from SHOULD to MUST. |
| G2 | Added Coinglass API/model behavior decision task. |
| U2 | Added calibration artifact contract and schema/audit tasks. |
| I2 | Documented Spec Kit `SPECIFY_FEATURE=033-public-liqmap-provider-parity` prerequisite usage in `plan.md`. |
