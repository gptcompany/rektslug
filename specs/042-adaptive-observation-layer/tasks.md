# Tasks: Adaptive Observation Layer for Expert Scorecard

**Input**: Design documents from `/specs/042-adaptive-observation-layer/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: TDD enforced per project constitution. RED tests before implementation.

**Organization**: Tasks grouped by user story for independent implementation.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1-US5)

---

## Phase 1: Setup

**Purpose**: Create new module files and extend existing models

- [ ] T001 Create `src/liquidationheatmap/scorecard/adaptive.py` with module docstring and imports
- [ ] T002 [P] Create `src/liquidationheatmap/scorecard/bootstrap.py` with module docstring and imports
- [ ] T003 [P] Create `tests/test_scorecard/test_adaptive.py` with imports
- [ ] T004 [P] Create `tests/test_scorecard/test_bootstrap.py` with imports
- [ ] T005 Extend `ExpertSignalObservation` in `src/liquidationheatmap/models/scorecard.py` with new optional fields: `adaptive_touch_band_bps`, `local_volatility_bps`, `volume_at_touch`, `volume_window_complete`, `post_touch_volume`, `inferred_regime`
- [ ] T006 Extend `ExpertScorecardBundle` in `src/liquidationheatmap/models/scorecard.py` with optional `adaptive_parameters` field
- [ ] T006a Extend `ExpertScorecardSlice` in `src/liquidationheatmap/models/scorecard.py` with optional `bucket_boundaries` field
- [ ] T006b Define `QuantileBucketSet` Pydantic model in `src/liquidationheatmap/models/scorecard.py` with fields: `metric_name`, `n_buckets`, `boundaries`, `labels`, `observation_count`
- [ ] T006c Define `BootstrapDominanceResult` Pydantic model in `src/liquidationheatmap/models/scorecard.py` with fields: `expert_a`, `expert_b`, `metric`, `p_a_better`, `significant`, `ci_lower`, `ci_upper`, `n_bootstrap`
- [ ] T007 Update `src/liquidationheatmap/scorecard/__init__.py` to export new modules

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core computation primitives that all user stories depend on

- [ ] T008 RED: write failing test for `compute_realized_volatility()` in `tests/test_scorecard/test_adaptive.py` — given a price path with known log-returns, expect correct vol in bps
- [ ] T009 Implement `compute_realized_volatility(price_path, timestamp, lookback_ticks) -> int` in `src/liquidationheatmap/scorecard/adaptive.py` — rolling std of log-returns from price path close prices
- [ ] T010 RED: write failing test that `compute_realized_volatility()` returns 0 when price path has fewer than 2 ticks
- [ ] T011 GREEN: handle edge case in `compute_realized_volatility()` for insufficient data
- [ ] T011b RED: write failing test in `tests/test_scorecard/test_adaptive.py` that validates the adaptive price path contract — `klines_1m_history`-shaped ticks with quote-currency `volume` are accepted, ticks without `volume` produce `volume=None` gracefully
- [ ] T011c GREEN: implement price path volume extraction helper in `src/liquidationheatmap/scorecard/adaptive.py`

**Checkpoint**: Volatility primitive and volume contract ready — user stories can begin

---

## Phase 3: User Story 1 — Adaptive Touch Detection (Priority: P1)

**Goal**: Touch tolerance band derived from local realized volatility, not fixed 5 bps

**Independent Test**: Same expert artifact produces different touch bands under different volatility conditions

### Tests for US1

- [ ] T012 [US1] RED: write failing test for `compute_adaptive_touch_band()` in `tests/test_scorecard/test_adaptive.py` — given low vol, expect narrow band; given high vol, expect wider band
- [ ] T013 [US1] RED: write failing test that two symbols with different volatility profiles produce different touch bands
- [ ] T014 [US1] RED: write failing test in `tests/test_scorecard/test_builder.py` for `apply_touch_detection()` with adaptive band — same level touched with wide band but not with narrow band

### Implementation for US1

- [ ] T015 [US1] Implement `compute_adaptive_touch_band(price_path, snapshot_ts, symbol) -> int` in `src/liquidationheatmap/scorecard/adaptive.py` — vol → touch band bps
- [ ] T016 [US1] Extend `ScorecardBuilder.apply_touch_detection()` in `src/liquidationheatmap/scorecard/builder.py` to accept optional `adaptive_band_fn` parameter; when provided, use it instead of fixed `TOUCH_TOLERANCE_BPS`
- [ ] T017 [US1] GREEN: verify all US1 tests pass
- [ ] T018 [US1] RED: write failing test for volatility proxy fallback in `tests/test_scorecard/test_adaptive.py` — when price path lacks sufficient history, use price spread as proxy (never fall back to fixed constant)
- [ ] T019 [US1] GREEN: implement volatility proxy fallback in `compute_adaptive_touch_band()`

**Checkpoint**: Adaptive touch detection works independently; fixed-band codepath preserved when adaptive disabled

---

## Phase 4: User Story 2 — Volume-Clock Observation Windows (Priority: P1)

**Goal**: Post-touch MFE/MAE evaluation window closes on cumulative volume, not fixed time

**Independent Test**: Same touch event with different volume profiles produces different wall-clock window durations

### Tests for US2

- [ ] T020 [US2] RED: write failing test for `compute_volume_threshold()` in `tests/test_scorecard/test_adaptive.py` — given price path with volume data, returns a volume threshold derived from the data
- [ ] T021 [US2] RED: write failing test in `tests/test_scorecard/test_builder.py` for `apply_post_touch_path()` with volume-clock — high-volume path closes window sooner than low-volume path
- [ ] T022 [US2] RED: write failing test that observations with insufficient post-touch volume are marked incomplete (`volume_window_complete=False`)

### Implementation for US2

- [ ] T023 [US2] Implement `compute_volume_threshold(price_path, snapshot_ts) -> float` in `src/liquidationheatmap/scorecard/adaptive.py` — volume threshold from empirical volume distribution
- [ ] T024 [US2] Extend `ScorecardBuilder.apply_post_touch_path()` in `src/liquidationheatmap/scorecard/builder.py` to accept optional volume-clock parameters; when provided, close window on volume threshold instead of `POST_TOUCH_WINDOW_HOURS`
- [ ] T025 [US2] GREEN: verify all US2 tests pass
- [ ] T026 [US2] RED: write failing test for volume data absent in price path — observations marked with `volume_window_complete=None` (FR-015)
- [ ] T027 [US2] GREEN: implement missing-volume fallback in `apply_post_touch_path()`
- [ ] T027b [US2] RED: write failing test that liquidation confirmation window uses volume-clock when adaptive enabled in `tests/test_scorecard/test_builder.py`
- [ ] T027c [US2] Extend `apply_liquidation_confirmation()` in `src/liquidationheatmap/scorecard/builder.py` to accept volume-clock window; when provided, replace fixed `LIQ_CONFIRM_WINDOW_MINUTES`
- [ ] T027d [US2] GREEN: verify liquidation confirmation volume-clock test passes

**Checkpoint**: Volume-clock windows work for both post-touch path and liquidation confirmation; time-based codepath preserved as fallback

---

## Phase 5: User Story 3 — Data-Derived Bucketing (Priority: P1)

**Goal**: Distance and confidence bucket boundaries from empirical quantiles, not hardcoded ranges

**Independent Test**: Skewed dataset produces different bucket boundaries than spec-041 defaults; each bucket has approximately equal observation count

### Tests for US3

- [ ] T028 [US3] RED: write failing test for `compute_quantile_buckets()` in `tests/test_scorecard/test_adaptive.py` — given a list of distance_bps values, returns quantile-based boundaries that differ from hardcoded [0-25, 25-50, ...]
- [ ] T029 [US3] RED: write failing test that quantile buckets produce approximately equal observation counts per bucket
- [ ] T030 [US3] RED: write failing test that sparse data (<min observations) falls back to single "all" bucket
- [ ] T031 [US3] RED: write failing test in `tests/test_scorecard/test_slicer.py` for `ScorecardSlicer` with quantile buckets — slice IDs use quantile-derived labels

### Implementation for US3

- [ ] T032 [US3] Implement `compute_quantile_buckets(values, metric_name, min_per_bucket) -> QuantileBucketSet` in `src/liquidationheatmap/scorecard/adaptive.py`
- [ ] T033 [US3] Extend `ScorecardSlicer` in `src/liquidationheatmap/scorecard/slicer.py` to accept optional `QuantileBucketSet` for distance and confidence; when provided, use quantile boundaries instead of hardcoded methods
- [ ] T034 [US3] GREEN: verify all US3 tests pass

**Checkpoint**: Quantile bucketing works independently; hardcoded bucket codepath preserved when adaptive disabled

---

## Phase 6: User Story 4 — Probabilistic Dominance (Priority: P2)

**Goal**: Expert-vs-expert dominance via bootstrap CI, not point-estimate winners

**Independent Test**: Two experts with similar performance on a slice produce "inconclusive" rather than declaring a winner

### Tests for US4

- [ ] T035 [US4] RED: write failing test for `bootstrap_dominance()` in `tests/test_scorecard/test_bootstrap.py` — given two clearly different observation sets, returns `significant=True` and `p_a_better` near 1.0
- [ ] T036 [US4] RED: write failing test that two similar observation sets return `significant=False`
- [ ] T037 [US4] RED: write failing test for deterministic reproducibility — same inputs + same seed produce identical bootstrap results (FR-013)
- [ ] T038 [US4] RED: write failing test that very few observations produce wide CI and `significant=False`

### Implementation for US4

- [ ] T039 [US4] Implement `bootstrap_dominance(obs_a, obs_b, metric_fn, n_bootstrap, seed, higher_is_better=True) -> BootstrapDominanceResult` in `src/liquidationheatmap/scorecard/bootstrap.py` — pairwise resampling with probability, CI, and explicit metric orientation
- [ ] T040 [US4] GREEN: verify all US4 tests pass

**Checkpoint**: Bootstrap dominance works independently; can be tested without adaptive touch or volume-clock

---

## Phase 7: User Story 5 — Data-Inferred Regime (Priority: P2)

**Goal**: Regime labels inferred from realized volatility quantiles, not manual labels

**Independent Test**: Dataset spanning a known vol-regime transition produces at least two distinct regime labels without manual input

### Tests for US5

- [ ] T041 [US5] RED: write failing test for `infer_regime_map()` in `tests/test_scorecard/test_adaptive.py` — given observations with varying volatility, returns at least two distinct regime labels
- [ ] T042 [US5] RED: write failing test that stable low-vol period produces uniform regime label
- [ ] T043 [US5] RED: write failing test that missing market feature data defaults to "unknown" regime (FR-010)

### Implementation for US5

- [ ] T044 [US5] Implement `infer_regime_map(observations, price_path) -> dict[datetime, str]` in `src/liquidationheatmap/scorecard/adaptive.py` — vol quantile → regime labels
- [ ] T045 [US5] Extend `ScorecardSlicer.__init__()` in `src/liquidationheatmap/scorecard/slicer.py` to accept inferred regime map (replaces manual `regime_map` when adaptive enabled)
- [ ] T046 [US5] GREEN: verify all US5 tests pass

**Checkpoint**: Regime inference works independently

---

## Phase 8: Pipeline Wiring & End-to-End

**Purpose**: Wire all adaptive primitives into the pipeline with `enable_adaptive` flag

- [ ] T047 Add `enable_adaptive` parameter to `ScorecardPipeline.run()` in `src/liquidationheatmap/scorecard/pipeline.py`
- [ ] T048 Wire adaptive touch band into pipeline when `enable_adaptive=True` in `src/liquidationheatmap/scorecard/pipeline.py`
- [ ] T049 Wire volume-clock post-touch path into pipeline when `enable_adaptive=True` in `src/liquidationheatmap/scorecard/pipeline.py`
- [ ] T050 Wire quantile buckets into pipeline when `enable_adaptive=True` in `src/liquidationheatmap/scorecard/pipeline.py`
- [ ] T051 Wire bootstrap dominance into `dominance_rows` when `enable_adaptive=True` in `src/liquidationheatmap/scorecard/pipeline.py`, preserving the existing bundle field name
- [ ] T052 Wire inferred regime into pipeline when `enable_adaptive=True` in `src/liquidationheatmap/scorecard/pipeline.py`
- [ ] T053 Include `adaptive_parameters` in bundle output when `enable_adaptive=True` in `src/liquidationheatmap/scorecard/pipeline.py`
- [ ] T054 Add `enable_adaptive` parameter to `run_from_retained_snapshots()` in `src/liquidationheatmap/scorecard/pipeline.py`
- [ ] T055 RED: write failing end-to-end test in `tests/test_scorecard/test_pipeline.py` — `enable_adaptive=True` produces different bucket boundaries, bootstrap dominance rows, and non-None adaptive_parameters
- [ ] T056 GREEN: verify end-to-end test passes
- [ ] T057 RED: write failing reproducibility test in `tests/test_scorecard/test_pipeline.py` — same inputs with `enable_adaptive=True` produce byte-identical output
- [ ] T058 GREEN: verify reproducibility test passes
- [ ] T059 RED: write failing backward compatibility test — `enable_adaptive=False` produces identical output to spec-041 baseline
- [ ] T060 GREEN: verify backward compatibility

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T061 Run `uv run ruff check` on all new and modified files
- [ ] T062 Run full test suite `uv run pytest tests/test_scorecard/ -v` and verify all tests pass
- [ ] T062b Benchmark `enable_adaptive=True` pipeline on 4 experts, 1 symbol, ~1000 observations — verify completes in <10s in `tests/test_scorecard/test_pipeline.py`
- [ ] T063 Verify SC-007: grep for hardcoded constants in adaptive codepath — zero fixed market threshold/band/bucket values outside documented computation-method constants
- [ ] T064 Update `specs/042-adaptive-observation-layer/checklists/requirements.md` with final pass/fail status

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — volatility primitive blocks all stories
- **Phase 3 (US1)**: Depends on Phase 2 — adaptive touch
- **Phase 4 (US2)**: Depends on Phase 2 — volume-clock (independent of US1)
- **Phase 5 (US3)**: Depends on Phase 2 — quantile buckets (independent of US1, US2)
- **Phase 6 (US4)**: Depends on Phase 2 — bootstrap dominance (independent of US1-US3)
- **Phase 7 (US5)**: Depends on Phase 2 — regime inference (independent of US1-US4)
- **Phase 8 (Pipeline)**: Depends on Phases 3-7 — wires everything together
- **Phase 9 (Polish)**: Depends on Phase 8

### User Story Independence

- **US1, US2, US3, US4, US5** can all proceed in parallel after Phase 2
- Each user story touches different functions/methods — no file conflicts between stories
- Pipeline wiring (Phase 8) is the integration point

### Parallel Opportunities

After Phase 2 completes:

**File ownership constraints**: US1, US2, US3, US5 all write to `adaptive.py`.
They MUST execute sequentially for `adaptive.py` writes. US4 writes only to
`bootstrap.py` and can run in parallel with any other story.

Recommended execution order:
```
Sequential on adaptive.py: US1 → US2 → US3 → US5
Parallel with any:          US4 (bootstrap.py only)
```

Safe parallel pairs:
- US4 (bootstrap.py) ‖ US1 (adaptive.py + builder.py)
- US4 (bootstrap.py) ‖ US2 (adaptive.py + builder.py)
- US4 (bootstrap.py) ‖ US3 (adaptive.py + slicer.py)
- US4 (bootstrap.py) ‖ US5 (adaptive.py + slicer.py)

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1: Setup
2. Phase 2: Foundational (volatility primitive)
3. Phase 3: US1 (adaptive touch detection)
4. **VALIDATE**: Different vol → different touch bands
5. Partial Phase 8: wire only adaptive touch into pipeline

### Incremental Delivery

1. Setup + Foundational → vol primitive ready
2. US1 → adaptive touch → validate
3. US2 → volume-clock → validate
4. US3 → quantile buckets → validate
5. US4 → bootstrap dominance → validate
6. US5 → inferred regime → validate
7. Phase 8 → full pipeline wiring → end-to-end validation
8. Phase 9 → polish

---

## Notes

- All adaptive features are opt-in via `enable_adaptive=True`
- spec-041 behavior is the default and must not break
- No external dependencies (numpy, scipy, sklearn) — stdlib only
- Bootstrap seed is deterministic per slice_id for reproducibility
- 72 total tasks across 9 phases (8 added from analyze remediation)
