# Plan: Nautilus Liquidation Bridge Operational Closeout (spec-037)

## Architecture

### Component Ownership

| Component | Repo | Key Files |
|-----------|------|-----------|
| Signal production, Redis publish | `rektslug` | `src/liquidationheatmap/signals/` |
| Feedback ingestion, DuckDB persist | `rektslug` | `src/liquidationheatmap/signals/`, `scripts/migrations/` |
| Runbooks, evidence package | `rektslug` | `docs/`, `specs/037-*/` |
| Nautilus strategy, order lifecycle | `nautilus_dev` | `strategies/hyperliquid/liquidation_bridge/` |
| Smoke/soak/continuous runners | `nautilus_dev` | `scripts/hyperliquid/` |
| Fault-injection hooks | `nautilus_dev` | `scripts/hyperliquid/`, strategy config |

### Evidence Schema

Phase 1 freezes the concrete schema, but the required shape is:

```json
{
  "run_type": "smoke|soak|continuous|recovery",
  "cycles": [
    {
      "cycle": 1,
      "signal_submitted": true,
      "position_opened": true,
      "position_closed": true,
      "feedback_persisted": true
    }
  ],
  "aggregate": {
    "passed": 20,
    "failed": 0,
    "feedback_rows": 20
  },
  "failures": [
    {
      "point": "post-submit",
      "source": "venue|bridge",
      "detail": "..."
    }
  ],
  "account_state": {
    "open_positions": 0,
    "open_orders": 0
  }
}
```

### Inter-Phase Dependencies

- Phase 2 depends on Phase 1 because long soak reports must use frozen schemas.
- Phase 3 depends on Phase 2 because real-signal execution should start only
  after repeated synthetic-cycle stability.
- Phase 4 depends on Phase 2 but is independent of Phase 3, so recovery tests can
  run in parallel after the soak contract is stable.
- Phase 5 depends on Phase 3 and Phase 4 because it aggregates continuous and
  recovery evidence.

## Phase 1: Contract Freeze

1. Freeze the operational boundary between `rektslug` and `nautilus_dev`.
2. Freeze promotion gates from dry-run through paper/testnet continuous.
3. Freeze required evidence outputs and failure semantics.

## Phase 2: Long Soak Hardening

1. Extend the existing guarded soak into a review-grade long soak profile:
   - short: `2` cycles for development smoke
   - standard: `20` cycles for pre-review
   - extended: `50` cycles or time-bounded equivalent for release evidence
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
