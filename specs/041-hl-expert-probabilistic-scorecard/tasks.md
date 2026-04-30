# Tasks: spec-041 Hyperliquid Expert Probabilistic Scorecard

## Phase 1: Contract Freeze

- [ ] T001 Freeze the primary expert set as `v1`, `v3`, `v4`, `v5`
- [ ] T002 Freeze `v2` as optional control-only input
- [ ] T003 Freeze the observation-row contract for event-level expert evaluation
- [ ] T004 Freeze the scorecard-slice contract for empirical probabilities and quantiles
- [ ] T005 Freeze touch, liquidation-confirmation, and post-touch window semantics

## Phase 2: Observation Dataset Builder

- [ ] T006R RED: write failing tests for observation extraction from retained expert artifacts
- [ ] T007 Build observation rows with `expert_id`, price level, side, confidence, and distance metadata
- [ ] T008R RED: write failing tests for touch detection and time-to-touch extraction
- [ ] T009 Implement touch detection against realized price path
- [ ] T010R RED: write failing tests for liquidation-confirmation matching after touch
- [ ] T011 Implement liquidation-confirmation matching against realized liquidation data

## Phase 3: Empirical Probability Engine

- [ ] T012R RED: write failing tests for empirical probability aggregation
- [ ] T013 Implement `P(touch | signal)` and `P(liquidation_confirmation | touch)`
- [ ] T014R RED: write failing tests for `MFE`, `MAE`, and time-to-event quantiles
- [ ] T015 Implement empirical `MFE`, `MAE`, `time_to_touch`, and `time_to_liquidation_confirm` summaries
- [ ] T016 Implement low-sample flags and explicit insufficient-data markers

## Phase 4: Slice and Comparison Layer

- [ ] T017R RED: write failing tests for slice aggregation by symbol, side, distance bucket, and confidence bucket
- [ ] T018 Implement scorecard slices for symbol/side/distance/confidence
- [ ] T019 Add optional volatility-regime slicing when labels are available
- [ ] T020 Implement expert-vs-expert dominance/comparison output per slice

## Phase 5: Historical and Incremental Integration

- [ ] T021 Define the historical backfill entry point from retained `expert_snapshots`
- [ ] T022R RED: write failing tests for append-safe incremental updates
- [ ] T023 Implement append-safe reruns and incremental observation ingestion
- [ ] T024 Keep execution-quality fields optional and clearly separated from signal-quality fields

## Phase 6: Artifacts and Review

- [ ] T025 Emit machine-readable scorecard bundles
- [ ] T026 Emit a compact markdown summary for reviewer entry points
- [ ] T027 Document ownership boundary: `rektslug` measures expert quality, `nautilus_dev` may consume but does not own this scorecard
- [ ] T028 Final review: confirm MVP does not collapse expert comparison into a single mandatory linear score

