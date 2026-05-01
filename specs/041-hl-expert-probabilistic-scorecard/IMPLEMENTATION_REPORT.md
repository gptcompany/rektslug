# spec-041 Implementation Report

Date: 2026-05-01
Status: Implemented, pending external review

## Scope

Implemented `spec-041` inside `rektslug` only. No `nautilus_dev` changes.

Covered capabilities:

- contract models and deterministic IDs
- observation extraction from retained Hyperliquid expert artifacts
- first-touch detection
- liquidation confirmation against a retained normalized event source contract
- empirical probability and quantile aggregation
- deterministic slicing by symbol/side/distance/confidence/regime
- expert-vs-expert dominance rows per slice
- historical backfill entry point from retained `expert_snapshots`
- append-safe deduplication by deterministic `observation_id`
- machine-readable bundle JSON
- compact markdown summary

## Files

Core implementation:

- [src/liquidationheatmap/models/scorecard.py](/media/sam/1TB/rektslug/src/liquidationheatmap/models/scorecard.py)
- [src/liquidationheatmap/scorecard/builder.py](/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/builder.py)
- [src/liquidationheatmap/scorecard/aggregator.py](/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/aggregator.py)
- [src/liquidationheatmap/scorecard/slicer.py](/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/slicer.py)
- [src/liquidationheatmap/scorecard/pipeline.py](/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/pipeline.py)
- [src/liquidationheatmap/scorecard/__init__.py](/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/__init__.py)

Retained source contract:

- [data/validation/liquidation_confirmation_events/README.md](/media/sam/1TB/rektslug/data/validation/liquidation_confirmation_events/README.md)

Tests:

- [tests/test_models/test_scorecard_models.py](/media/sam/1TB/rektslug/tests/test_models/test_scorecard_models.py)
- [tests/test_scorecard/test_builder.py](/media/sam/1TB/rektslug/tests/test_scorecard/test_builder.py)
- [tests/test_scorecard/test_liquidation_confirmation.py](/media/sam/1TB/rektslug/tests/test_scorecard/test_liquidation_confirmation.py)
- [tests/test_scorecard/test_aggregation.py](/media/sam/1TB/rektslug/tests/test_scorecard/test_aggregation.py)
- [tests/test_scorecard/test_slicer.py](/media/sam/1TB/rektslug/tests/test_scorecard/test_slicer.py)
- [tests/test_scorecard/test_pipeline.py](/media/sam/1TB/rektslug/tests/test_scorecard/test_pipeline.py)

Spec bookkeeping:

- [spec.md](/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/spec.md)
- [tasks.md](/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/tasks.md)

## Verification

Executed:

```bash
uv run pytest -q tests/test_models/test_scorecard_models.py tests/test_scorecard
uv run ruff check src/liquidationheatmap/models/scorecard.py src/liquidationheatmap/scorecard tests/test_models/test_scorecard_models.py tests/test_scorecard
```

Observed:

- `26 passed`
- `ruff` clean

Retained smoke:

- `ScorecardPipeline.run_from_retained_snapshots(...)` against one real retained BTC manifest
- bundle validated successfully
- sample smoke output:
  - `47` slices
  - `12` dominance rows
  - `0` missing artifacts for the sampled manifest

## Review Notes

Important contract decisions:

- `observation_id` is deterministic UUID5 over:
  - `expert_id + symbol + snapshot_ts + level_price + side`
- `slice_id` is deterministic:
  - `{expert_id}:{symbol}:{side}:{distance_bucket}:{confidence_bucket}:{regime}`
- touch semantics are first-touch only
- liquidation confirmation source is retained and explicit, not inferred from WS
- scorecard stays non-linear and distributional; no mandatory global scalar winner

## Residual Notes

- Repo still contains unrelated dirty files from the Hyperliquid WS cleanup thread outside this scorecard scope.
- This report only covers the `spec-041` implementation surface.
