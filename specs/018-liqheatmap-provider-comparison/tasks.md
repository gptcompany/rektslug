# Tasks: Provider Liq-Heat-Map Comparison

**Input**: `specs/018-liqheatmap-provider-comparison/spec.md`
**Dependencies**: `spec-016` runtime gates, `spec-017` comparison harness patterns
**Feature Type**: Validation/comparison workflow

## Phase 1: Scope Lock

- [ ] T001 Confirm heatmap matrix: `BTC/ETH x 48h/7d`
- [ ] T002 Confirm local runtime gates (`rektslug-api`, `rektslug-sync`, DuckDB freshness)
- [ ] T003 [P] Confirm `dotenvx` secrets required by CoinAnk/Coinglass capture scripts
- [ ] T004 [P] Confirm Playwright/Chromium availability for browser fallback capture

## Phase 2: Product Guardrails

- [ ] T005 Add `spec-018` preset to `scripts/run_provider_api_comparison.py`
- [ ] T006 Enforce `--product liq-heat-map` filtering in comparison selection
- [ ] T007 Ensure manifests/report entries always carry `product=liq-heat-map`
- [ ] T008 Reject `liq-map` captures in `spec-018` runs (hard fail)

## Phase 3: Matrix Contract

- [ ] T009 Add contract tests for supported windows (`48h`, `7d`) and symbols (`BTC`, `ETH`)
- [ ] T010 Fail fast for unsupported windows/symbols under `spec-018`
- [ ] T011 Thread matrix metadata (`symbol`, `window`, `product`) through manifest + report

## Phase 4: CoinAnk Heatmap Capture

- [ ] T012 Validate CoinAnk heatmap URL generation for `48h` and `7d`
- [ ] T013 Capture CoinAnk heatmap payload/screenshot with explicit product tagging
- [ ] T014 Ensure CoinAnk heatmap artifacts are kept separate from liq-map artifacts

## Phase 5: Coinglass Heatmap Capture

- [ ] T015 Identify and lock Coinglass heatmap endpoint mapping used in repo docs/scripts
- [ ] T016 Implement capture path with REST-first and browser fallback
- [ ] T017 Add parser normalization for Coinglass heatmap payload shape
- [ ] T018 Add tests for decode/parse drift handling

## Phase 6: Local Heatmap Normalization & Comparison

- [ ] T019 Normalize local heatmap payload into the common heatmap schema
- [ ] T020 Emit 3-provider comparison report (`rektslug`, `coinank`, `coinglass`)
- [ ] T021 Add heatmap-specific gap analysis scenario output
- [ ] T022 Persist summary rows to validation DB when persistence mode is enabled

## Phase 7: Baselines

- [ ] T023 Run baseline BTC 48h
- [ ] T024 Run baseline BTC 7d
- [ ] T025 Run baseline ETH 48h
- [ ] T026 Run baseline ETH 7d
- [ ] T027 Verify all baseline artifacts are heatmap-only (no liq-map contamination)

## Phase 8: Docs & Closeout

- [ ] T028 Update `docs/provider-api-comparison.md` with the `spec-018` workflow
- [ ] T029 [P] Update route/runbook references for heatmap matrix commands
- [ ] T030 [P] Add artifact checklist for `liq-heat-map` run acceptance

## Notes

- Keep this spec isolated from `spec-017`.
- If provider endpoints drift, update scripts/docs but do not widen scope beyond `48h/7d` and BTC/ETH.
