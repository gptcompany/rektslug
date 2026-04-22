# Evidence Package: spec-040 Nautilus Continuous Paper/Testnet Runtime

**Status**: Implemented with retained G3 evidence
**Created**: 2026-04-22

This package records the current closeout state for spec-040.

What is implemented in-repo:

- continuous runtime wiring in `nautilus_dev`
- `rektslug-feedback-consumer` as a compose-managed service
- fail-closed continuous report contract in `rektslug`
- explicit mismatch gating for `feedback_published` vs `feedback_persisted`
- reconciliation tooling to build a review package from runtime snapshot + DuckDB

Retained operational evidence now exists:

- real G3 session: `specs/040-nautilus-continuous-paper-testnet/g3_session/20260422T212929Z/`
- retained evidence summary: `.../g3_session/20260422T212929Z/evidence/summary.json`
- retained evidence report: `.../g3_session/20260422T212929Z/evidence/report.md`
- lifecycle closure from real `rektslug` Redis signal:
  - `signals_seen=1`
  - `signals_accepted=1`
  - `positions_opened=1`
  - `positions_closed=1`
  - `feedback_published=1`
  - `feedback_persisted=1`

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
| `G3` continuous paper/testnet | Ready for review | retained real session at `g3_session/20260422T212929Z/` with reconciled evidence |
| `G4` external review | Ready for code review | review entry points updated in readiness docs |

## Reconciliation Command

Build the review package from a real runtime snapshot and feedback DuckDB:

```bash
cd /media/sam/1TB/rektslug
uv run python scripts/build_spec040_evidence.py \
  --runtime-snapshot-path specs/040-nautilus-continuous-paper-testnet/g3_session/20260422T212929Z/continuous_runtime_report.json \
  --db-path /media/sam/2TB-NVMe/liquidationheatmap_db/signal_feedback.duckdb \
  --output-dir specs/040-nautilus-continuous-paper-testnet/evidence
```

Outputs:

- `specs/040-nautilus-continuous-paper-testnet/evidence/summary.json`
- `specs/040-nautilus-continuous-paper-testnet/evidence/report.md`

The builder fails closed if the runtime snapshot is missing or if
`feedback_persisted` cannot be measured from DuckDB.

## Retained G3 Session

Retained successful session:

- session dir:
  `specs/040-nautilus-continuous-paper-testnet/g3_session/20260422T212929Z/`
- result:
  `session_result.json`
- evidence:
  `evidence/summary.json`
  `evidence/report.md`

Session facts:

- mode: `testnet`
- symbol: `BTCUSDT`
- signal id: `spec040-g3-1776893370`
- session_started_at: `2026-04-22T21:29:32.025255Z`
- gate_status: `READY_FOR_REVIEW`
- report_status: `ok`
- report_matches_duckdb: `true`
- residual_open_positions: `0`
- residual_open_orders: `0`

Secret review:

- no `HYPERLIQUID_TESTNET_PK` match in retained session artifacts
- no raw `0x...` 64-byte private key match in retained session artifacts

## Reviewer Entry Points

Reviewers should inspect these first:

1. `nautilus_dev/scripts/hyperliquid/run_continuous.py`
2. `nautilus_dev/strategies/hyperliquid/liquidation_bridge/strategy.py`
3. `src/liquidationheatmap/signals/feedback.py`
4. `src/liquidationheatmap/api/routers/signals.py`
5. `scripts/build_spec040_evidence.py`
6. `tests/integration/test_build_spec040_evidence.py`

## Closeout

Spec-040 now has:

- implemented runtime wiring in `nautilus_dev`
- compose-managed feedback persistence in `rektslug`
- fail-closed report contract with blocking mismatch detection
- retained real G3 session evidence with non-zero lifecycle closure
- DuckDB reconciliation against `signal_feedback`
- explicit secret-scan pass for retained artifacts
