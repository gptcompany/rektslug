# Plan: Nautilus Liquidation Bridge Operational Closeout (spec-037)

## Phase 1: Contract Freeze

1. Freeze the operational boundary between `rektslug` and `nautilus_dev`.
2. Freeze promotion gates from dry-run through paper/testnet continuous.
3. Freeze required evidence outputs and failure semantics.

## Phase 2: Long Soak Hardening

1. Extend the existing guarded soak into a review-grade long soak profile.
2. Retain aggregate and per-cycle JSON evidence.
3. Enforce post-run venue cleanup checks as hard failures.
4. Add runbook guidance for recommended cycle counts and interpretation.

## Phase 3: Real-Signal Paper/Testnet Continuous Mode

1. Run the Nautilus bridge against real `rektslug` signal channels.
2. Support dry-run decision recording before any testnet execution.
3. Support testnet execution with conservative thresholds and allowlists.
4. Persist lifecycle outcomes and feedback rows for every accepted signal.

## Phase 4: Recovery And Fault Injection

1. Add controlled failure points around submit/fill/open/close/feedback.
2. Validate restart behavior and cleanup under each failure point.
3. Verify Redis and DuckDB degradation paths fail closed.
4. Retain recovery reports for review.

## Phase 5: Metrics And Evidence Package

1. Aggregate signal, execution, feedback, cleanup, and latency metrics.
2. Produce a final machine-readable summary.
3. Produce human-readable evidence package and residual-risk summary.
4. Mark the spec complete only after all gates through `G4` are satisfied.
