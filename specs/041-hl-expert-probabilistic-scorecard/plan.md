# Implementation Plan: Hyperliquid Expert Probabilistic Scorecard

## Summary

Build an empirical scorecard for Hyperliquid experts `v1`, `v3`, `v4`, and
`v5` inside `rektslug`. The pipeline should transform retained expert artifacts
plus realized market/liquidation data into event-level observations and
machine-readable probability slices. MVP deliberately avoids a single weighted
linear score.

## Phase 1: Contract Freeze

1. Freeze the four-expert scope (`v1`, `v3`, `v4`, `v5`) and keep `v2` optional.
2. Freeze the observation row schema and scorecard slice schema.
3. Freeze first-touch, liquidation-confirmation, and post-touch window semantics.

## Phase 2: Observation Dataset Builder

1. Build event rows from retained expert artifacts.
2. Attach realized price-path outcomes per observation.
3. Attach realized liquidation-confirmation outcomes per observation.

## Phase 3: Empirical Probability Engine

1. Compute touch probabilities and conditional liquidation probabilities.
2. Compute empirical quantiles for `MFE`, `MAE`, and time-to-event metrics.
3. Mark low-sample slices explicitly instead of fabricating stability.

## Phase 4: Slice and Comparison Layer

1. Aggregate by symbol, side, distance bucket, and confidence bucket.
2. Add optional volatility-regime slicing when labels are available.
3. Produce expert-vs-expert dominance comparisons per slice.

## Phase 5: Runtime and Historical Integration

1. Support historical backfill from retained expert artifacts.
2. Support append-safe incremental updates from new shadow observations.
3. Keep execution-quality fields optional and separate from signal-quality metrics.

## Phase 6: Review Artifacts

1. Emit machine-readable scorecard bundles.
2. Emit compact markdown summaries for human review.
3. Document where `rektslug` ends and where `nautilus_dev` may consume the output.

## Ownership

| Capability | Owner | Notes |
| --- | --- | --- |
| Expert artifact production | `rektslug` | Already present via spec-029 path |
| Observation dataset generation | `rektslug` | New in this spec |
| Probabilistic scorecard | `rektslug` | New in this spec |
| Execution runtime / operator gate | `nautilus_dev` | Out of scope here |

## Output Targets

- Observation dataset artifact, likely JSONL or Parquet-equivalent structured export
- Scorecard bundle JSON
- Optional markdown comparison summary

## Explicit Non-Goals

- No global weighted rank in MVP
- No automatic live expert switching in MVP
- No ownership change for execution/runtime gates

