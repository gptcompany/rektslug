Review only `spec-041` implementation in `rektslug`.

Repository:
- `/media/sam/1TB/rektslug`

Scope:
- Hyperliquid expert probabilistic scorecard only
- do not review unrelated Hyperliquid WS cleanup files unless they directly affect `spec-041`
- do not suggest `nautilus_dev` changes

Authoritative spec files:
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/spec.md`
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/plan.md`
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/tasks.md`
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/IMPLEMENTATION_REPORT.md`

Primary implementation files:
- `/media/sam/1TB/rektslug/src/liquidationheatmap/models/scorecard.py`
- `/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/builder.py`
- `/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/aggregator.py`
- `/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/slicer.py`
- `/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/pipeline.py`
- `/media/sam/1TB/rektslug/data/validation/liquidation_confirmation_events/README.md`

Primary tests:
- `/media/sam/1TB/rektslug/tests/test_models/test_scorecard_models.py`
- `/media/sam/1TB/rektslug/tests/test_scorecard/test_builder.py`
- `/media/sam/1TB/rektslug/tests/test_scorecard/test_liquidation_confirmation.py`
- `/media/sam/1TB/rektslug/tests/test_scorecard/test_aggregation.py`
- `/media/sam/1TB/rektslug/tests/test_scorecard/test_slicer.py`
- `/media/sam/1TB/rektslug/tests/test_scorecard/test_pipeline.py`

Implemented commit chain to review:
- `53ff296 specs: add hyperliquid expert probabilistic scorecard`
- `f0a3f62 specs: tighten expert scorecard contracts`
- `736c104 docs: add gemini implementation prompt for spec-041`
- `3845d36 feat(scorecard): add scorecard contract models`
- `dd3139f fix(scorecard): enforce contract invariants`
- `f0cc98a feat(scorecard): extract observations and detect touches`
- `04a361b fix(scorecard): align builder with expert artifact contract`
- `cb15a74 feat(scorecard): add liquidation confirmation and coverage metadata`
- `b3497f3 fix(scorecard): tighten liquidation confirmation contract`
- `b373d21 feat(scorecard): aggregate empirical probabilities and quantiles`
- `611fab4 feat(scorecard): emit expert scorecards and incremental pipeline`
- `THIS_COMMIT final fix pass for Slice D/E, bookkeeping, and report/prompt`

Review goals:
1. Verify the implementation satisfies `spec-041` end to end.
2. Focus on bugs, contract drift, false-green tests, missing required outputs, and spec mismatches.
3. Confirm or challenge these specific claims:
   - deterministic IDs are enforced
   - retained expert artifact contract is used, not a toy schema
   - liquidation confirmation source is explicit and retained
   - `time_to_liquidation_confirm` summaries are emitted in the bundle
   - expert-vs-expert dominance rows are real, not placeholders
   - historical backfill entry point exists from retained `expert_snapshots`
   - no mandatory global linear score is introduced
4. Ignore style nits unless they hide a real contract or runtime problem.

Checks already run locally:
- `uv run pytest -q tests/test_models/test_scorecard_models.py tests/test_scorecard`
- `uv run ruff check src/liquidationheatmap/models/scorecard.py src/liquidationheatmap/scorecard tests/test_models/test_scorecard_models.py tests/test_scorecard`
- retained smoke via `ScorecardPipeline.run_from_retained_snapshots(...)`

Please answer in review mode:
- findings first, ordered by severity
- include file/line references
- explicitly state whether `spec-041` is review-closeable or not
