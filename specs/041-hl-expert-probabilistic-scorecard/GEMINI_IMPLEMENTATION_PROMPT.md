# Gemini Implementation Prompt: spec-041 Hyperliquid Expert Probabilistic Scorecard

Implement `spec-041` in `rektslug`.

Repository:
- `/media/sam/1TB/rektslug`

Authoritative inputs:
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/spec.md`
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/plan.md`
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/tasks.md`

Frozen baseline commits:
- `53ff296 specs: add hyperliquid expert probabilistic scorecard`
- `f0a3f62 specs: tighten expert scorecard contracts`

## Goal

Build an empirical, non-linear, machine-readable scorecard for Hyperliquid
experts `v1`, `v3`, `v4`, and `v5`.

Do **not** build:
- a single weighted linear score
- automatic live routing
- any `nautilus_dev` changes

## Hard Rules

- Implement only `spec-041`.
- Make exactly **one commit per slice**.
- Stop after each slice and report.
- Follow TDD for every `RED` task.
- Do not invent undeclared data sources.
- Do not assume an implicit "WS archive".
- Freeze one concrete persisted liquidation-confirmation source during implementation.
- Keep execution-quality fields optional and clearly separate from signal-quality metrics.
- Do not touch `nautilus_dev`.
- Do not refactor unrelated files.

## Required Style

- Use Pydantic v2 `BaseModel`, not dataclasses, for scorecard models.
- Use `pathlib.Path`.
- Keep output machine-readable first.
- Prefer small, explicit modules over large scripts.

## Required Source Semantics

Freeze these implementation choices explicitly in code and tests:

- touch price-path source:
  - `klines_1m_history`
  - `aggtrades_history` for tick-level touch refinement
- liquidation-confirmation source:
  - one explicit persisted normalized liquidation-event source
  - table name or retained artifact path must be declared in code/tests
  - no "best effort" archive guessing

## Slice Order

### Slice A: Contract Models and Constants

Tasks:
- `T001`
- `T002`
- `T003`
- `T004`
- `T005`

Scope:
- add `src/liquidationheatmap/models/scorecard.py`
- define:
  - `ExpertSignalObservation`
  - `ExpertScorecardSlice`
  - `ExpertScorecardBundle`
- define constants:
  - `TOUCH_WINDOW_HOURS=4`
  - `LIQ_CONFIRM_WINDOW_MINUTES=15`
  - `POST_TOUCH_WINDOW_HOURS=1`
  - `TOUCH_TOLERANCE_BPS=5`
- encode deterministic id semantics:
  - `observation_id` includes `expert_id + symbol + snapshot_ts + level_price + side`
  - `slice_id` follows spec

Tests/checks required:
- model validation tests
- schema serialization tests

Commit message:
- `feat(scorecard): add scorecard contract models`

Stop after this slice.

---

### Slice B: Observation Extraction and Touch Detection

Tasks:
- `T006R`
- `T007`
- `T007b`
- `T008R`
- `T009`

Scope:
- build observation extraction from retained expert artifacts
- preserve `touched=false` rows
- implement first-touch semantics only
- compute:
  - `reference_price`
  - `distance_bps`
  - `touched`
  - `touch_ts`
  - `time_to_touch_secs`

Tests/checks required:
- RED first, then GREEN
- explicit test for non-touch preservation
- explicit multiple-touch -> first-touch test

Commit message:
- `feat(scorecard): extract observations and detect touches`

Stop after this slice.

---

### Slice C: Liquidation Confirmation and Coverage Metadata

Tasks:
- `T010R`
- `T011`
- `T011b`
- `T024b`

Scope:
- freeze one concrete persisted normalized liquidation-event source
- implement liquidation confirmation matching after touch
- add coverage metadata:
  - per-expert artifact availability
  - liquidation-stream/source availability per window

Tests/checks required:
- RED first for confirmation matching
- tests proving the chosen persisted source is used
- tests proving missing source coverage is explicit, not fabricated

Commit message:
- `feat(scorecard): add liquidation confirmation and coverage metadata`

Stop after this slice.

---

### Slice D: Probability and Quantile Aggregation

Tasks:
- `T012R`
- `T013`
- `T014R`
- `T015`
- `T016`

Scope:
- compute:
  - `P(touch | signal)`
  - `P(liquidation_confirmation | touch)`
  - `MFE` quantiles
  - `MAE` quantiles
  - `time_to_touch` quantiles
  - `time_to_liquidation_confirm` quantiles
- enforce low-sample flags
- `MFE` / `MAE` in integer bps

Tests/checks required:
- RED first
- quantile tests
- low-sample tests

Commit message:
- `feat(scorecard): aggregate empirical probabilities and quantiles`

Stop after this slice.

---

### Slice E: Slice Layer, Incremental Idempotency, and Artifacts

Tasks:
- `T017R`
- `T018`
- `T019`
- `T020`
- `T021`
- `T022R`
- `T023`
- `T024`
- `T025`
- `T026`
- `T026b`
- `T026c`
- `T027`
- `T028`

Scope:
- aggregate by:
  - symbol
  - side
  - distance bucket
  - confidence bucket
  - optional regime
- implement expert-vs-expert dominance output
- implement historical backfill entry point
- implement append-safe reruns
- idempotency key:
  - `(expert_id, symbol, snapshot_ts, level_price, side)`
- emit:
  - machine-readable scorecard bundle JSON
  - compact markdown summary
- validate bundle against Pydantic schema
- add reproducibility test for byte-identical output on same inputs
- confirm final review condition:
  - no mandatory global linear score

Tests/checks required:
- RED first where declared
- schema validation test
- reproducibility test

Commit message:
- `feat(scorecard): emit expert scorecards and incremental pipeline`

Stop after this slice.

## Required Final Response Format For Every Slice

- Changed files
- Tests/checks run
- Commit hash
- Result
- Remaining risks or blockers

## Explicit Failure Conditions

Stop and report instead of guessing if:
- the liquidation-confirmation persisted source cannot be concretely identified
- retained expert artifact shape is missing fields required by the spec
- implementation would require changing `nautilus_dev`
- you cannot preserve `touched=false` observations

