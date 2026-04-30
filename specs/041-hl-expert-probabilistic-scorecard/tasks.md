# Tasks: spec-041 Hyperliquid Expert Probabilistic Scorecard

## Phase 1: Contract Freeze

- [ ] T001 Freeze the primary expert set as `v1`, `v3`, `v4`, `v5`
- [ ] T002 Freeze `v2` as optional control-only input
- [ ] T003 Define `ExpertSignalObservation` as a Pydantic v2 `BaseModel` in `src/liquidationheatmap/models/scorecard.py` matching the observation-row contract
- [ ] T004 Define `ExpertScorecardSlice` and `ExpertScorecardBundle` as Pydantic v2 `BaseModel` models in `src/liquidationheatmap/models/scorecard.py` matching the slice contract
- [ ] T005 Define window constants in `src/liquidationheatmap/models/scorecard.py`: `TOUCH_WINDOW_HOURS=4`, `LIQ_CONFIRM_WINDOW_MINUTES=15`, `POST_TOUCH_WINDOW_HOURS=1`, `TOUCH_TOLERANCE_BPS=5`; document first-touch semantics

## Phase 2: Observation Dataset Builder

- [ ] T006R RED: write failing tests for observation extraction from retained expert artifacts
- [ ] T007 Build observation rows with `expert_id`, price level, side, confidence, and distance metadata
- [ ] T007b RED: write failing test that observations with `touched=false` are preserved in the dataset (FR-004)
- [ ] T008R RED: write failing tests for touch detection and time-to-touch extraction (include edge case: multiple touches use first-touch semantics)
- [ ] T009 Implement touch detection against realized price path
- [ ] T010R RED: write failing tests for liquidation-confirmation matching after touch
- [ ] T011 Implement liquidation-confirmation matching against realized liquidation data
- [ ] T011b Define data source mapping: `klines_1m_history` for price path, `aggtrades_history` for tick-level touch, and one explicit persisted normalized liquidation-event source for confirmation events (table or retained artifact path must be frozen; no implicit WS archive)

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
- [ ] T024b Implement coverage and missing-data metadata: track per-expert artifact availability and liquidation-stream availability per observation window (FR-013)

## Phase 6: Artifacts and Review

- [ ] T025 Emit machine-readable scorecard bundles
- [ ] T026 Emit a compact markdown summary for reviewer entry points
- [ ] T026b RED: write test that scorecard bundle JSON validates against Pydantic model schema (NFR-002)
- [ ] T026c RED: write reproducibility test — same input artifacts produce byte-identical scorecard output (NFR-001)
- [ ] T027 Document ownership boundary: `rektslug` measures expert quality, `nautilus_dev` may consume but does not own this scorecard
- [ ] T028 Final review: confirm MVP does not collapse expert comparison into a single mandatory linear score
