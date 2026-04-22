# Evidence Package: spec-040 Nautilus Continuous Paper/Testnet Runtime

**Status**: Partial
**Created**: 2026-04-22

This package records the current closeout state for spec-040.

What is implemented in-repo:

- continuous runtime wiring in `nautilus_dev`
- `rektslug-feedback-consumer` as a compose-managed service
- fail-closed continuous report contract in `rektslug`
- explicit mismatch gating for `feedback_published` vs `feedback_persisted`
- reconciliation tooling to build a review package from runtime snapshot + DuckDB

What is still operational:

- a retained G3 continuous session with non-zero lifecycle closure from real `rektslug` signals

Do not mark spec-040 fully implemented until the operational gap below is closed
with concrete retained artifacts.

## Commit Ledger

### rektslug

- `ebf671a` spec-040 baseline
- `36794dc` acceptance/task coverage tightening
- `3c42451` feedback-consumer service wiring
- `127397e` runtime hardening for feedback consumer
- `76a3694` healthcheck fail-on-dependencies
- `067791c` continuous report contract
- `2dea6be` fail-closed continuous report baseline
- `84912b7` blocking status and explicit mismatch gating

### nautilus_dev

- `1ad2bd2` continuous runtime service
- `2ea96b2` runtime counters and mode guard
- `31aa8a8` recovery/fail-closed behavior
- `8868574` stronger T026B async-boundary evidence under load

## Current Gate View

| Gate | Status | Evidence |
|------|--------|----------|
| `G0` dry-run | Covered by continuous runtime tests | `nautilus_dev/tests/hyperliquid/test_continuous_runtime.py` |
| `G1` smoke | Existing baseline | `docs/runbooks/nautilus-liquidation-bridge-live-smoke.md` |
| `G2` soak | Existing baseline from spec-037 | `specs/037-nautilus-liquidation-bridge-operational-closeout/EVIDENCE_PACKAGE.md` |
| `G3` continuous paper/testnet | Partial | runtime/reporting/reconciliation implemented; retained real session pending |
| `G4` external review | Ready for code review | review entry points updated in readiness docs |

## Reconciliation Command

Build the review package from a real runtime snapshot and DuckDB:

```bash
cd /media/sam/1TB/rektslug
uv run python scripts/build_spec040_evidence.py \
  --runtime-snapshot-path /media/sam/2TB-NVMe/liquidationheatmap_db/continuous_runtime_report.json \
  --db-path /media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb \
  --output-dir specs/040-nautilus-continuous-paper-testnet/evidence
```

Outputs:

- `specs/040-nautilus-continuous-paper-testnet/evidence/summary.json`
- `specs/040-nautilus-continuous-paper-testnet/evidence/report.md`

The builder fails closed if the runtime snapshot is missing or if
`feedback_persisted` cannot be measured from DuckDB.

## Reviewer Entry Points

Reviewers should inspect these first:

1. `nautilus_dev/scripts/hyperliquid/run_continuous.py`
2. `nautilus_dev/strategies/hyperliquid/liquidation_bridge/strategy.py`
3. `src/liquidationheatmap/signals/feedback.py`
4. `src/liquidationheatmap/api/routers/signals.py`
5. `scripts/build_spec040_evidence.py`
6. `tests/integration/test_build_spec040_evidence.py`

## Operational Gap

The remaining unclosed part is not code shape. It is retained runtime evidence:

- run the continuous testnet service against real `rektslug` Redis signals
- retain a runtime snapshot with non-zero lifecycle closure
- reconcile that snapshot against `signal_feedback`
- attach the generated `summary.json` and `report.md`

Until that run exists, spec-040 should be treated as:

- implemented in code
- reviewable for architecture and fail-closed behavior
- pending operational G3 retention
