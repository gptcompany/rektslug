# Plan: Nautilus Continuous Paper/Testnet Runtime (spec-040)

## Architecture

### Frozen Deployment Decision

Spec-040 accepts `systemd-separated Nautilus service` as the first deployment
shape.

Implication:

- `nautilus_dev` runs the continuous paper/testnet execution runtime as its own
  long-running systemd service
- `rektslug` does not absorb the Nautilus runtime into its core image in the
  first iteration
- `rektslug` still owns the signal/reporting side and must add a separate
  feedback consumer service on its own side

The feedback consumer is also frozen as a separate service. It is not attached
to `rektslug-shadow-consumer` in the first iteration.
It is deployed in `rektslug` Docker Compose, not as a separate host systemd
unit.

### Implementation Boundary

The plan must keep these responsibilities explicit:

- `rektslug`: feedback persistence service, reporting, monitoring, evidence
- `nautilus_dev`: continuous execution service, venue lifecycle, reconciliation

### Component Ownership

| Component | Repo | Key Files / Areas |
|-----------|------|-------------------|
| Signal production, Redis publish | `rektslug` | `src/liquidationheatmap/signals/`, `scripts/run-shadow-producer.sh` |
| Feedback contract, DuckDB persistence | `rektslug` | `src/liquidationheatmap/signals/feedback.py`, `scripts/migrations/` |
| Shadow validation, reporting, circuit breaker | `rektslug` | `scripts/continuous_consumer.py`, `src/liquidationheatmap/signals/` |
| Continuous execution runtime | `nautilus_dev` | live/testnet runner, strategy config, runtime service |
| Venue connectivity and execution reconciliation | `nautilus_dev` | Nautilus `TradingNode`, Hyperliquid adapter/runtime |
| Runbooks and evidence package | `rektslug` + `nautilus_dev` | `docs/`, `specs/040-*`, downstream runtime docs |

### Runtime Topology

Recommended first iteration:

- `rektslug` continues as the production signal/reporting service
- `redis` remains the shared transport boundary
- `nautilus_dev` runs a dedicated continuous paper/testnet service outside the
  `rektslug` core image
- `rektslug` adds an always-on feedback consumer service with its own runtime
  boundary, healthcheck, and failure surface

Target loop:

```text
rektslug signal
  -> Redis liquidation:signals:{symbol}
  -> Nautilus continuous service
  -> venue execution / paper-testnet lifecycle
  -> Redis liquidation:feedback:{symbol}
  -> rektslug feedback consumer
  -> DuckDB signal_feedback + reporting
```

### Why Systemd-First

The accepted deployment shape is a systemd-managed Nautilus service, not a
first-pass merge into `rektslug` Docker Compose.

Reasoning:

- preserves the current multi-repo ownership boundary
- respects Nautilus nightly service guidance:
  - standalone script/service
  - one `TradingNode` per process
  - no notebook runtime
- avoids forcing a Python `3.12+` live-trading runtime into the existing
  `rektslug` core image prematurely
- keeps production rollback simpler during paper/testnet hardening
- keeps feedback persistence inside the existing `rektslug` compose deployment

### Phase 1 Exit Artifacts

Phase 1 is complete only when these are frozen:

- accepted service topology
- ownership boundary
- lifecycle-state contract
- mandatory continuous counters
- fail-closed conditions for green runs
- feedback-consumer separation from `rektslug-shadow-consumer`
- feedback-consumer placement in `rektslug` Docker Compose

### Evidence Schema

The continuous-runtime report should be machine-readable and must not use
placeholder counters:

```json
{
  "run_type": "continuous_paper|continuous_testnet",
  "window": {
    "started_at": "2026-04-21T20:00:00Z",
    "ended_at": "2026-04-21T22:00:00Z"
  },
  "signals": {
    "seen": 0,
    "rejected": 0,
    "accepted": 0
  },
  "orders": {
    "submitted": 0,
    "rejected": 0,
    "filled": 0
  },
  "positions": {
    "opened": 0,
    "closed": 0,
    "residual_open_positions": 0,
    "residual_open_orders": 0
  },
  "feedback": {
    "published": 0,
    "persisted": 0
  },
  "failures": [
    {
      "source": "venue|bridge|persistence|runtime",
      "stage": "order_submit|close|feedback_persist",
      "detail": "..."
    }
  ]
}
```

## Inter-Phase Dependencies

- Phase 2 depends on Phase 1 because deployment shape must be frozen before
  wiring runtime code or ops.
- Phase 3 depends on Phase 2 because the feedback consumer must be defined
  before persistence and reporting can be trusted.
- Phase 4 depends on Phase 2 and Phase 3 because runtime wiring needs service
  topology and persistence boundaries.
- Phase 5 depends on Phase 4 because recovery tests need the final service
  topology.
- Phase 6 depends on Phase 4 and Phase 5 because evidence needs real runtime and
  recovery behavior.

## Phase 1: Contract Freeze

1. Freeze the runtime boundary between `rektslug` and `nautilus_dev`.
2. Freeze required lifecycle states, counters, and fail-closed behavior.
3. Freeze G3 acceptance semantics for continuous paper/testnet.

## Phase 2: Service Topology

1. Define the Nautilus continuous service contract in `nautilus_dev`.
2. Define the `rektslug-feedback-consumer` service contract as a distinct
   compose-managed service.
3. Freeze secret injection and environment separation for paper/testnet.
4. Freeze healthcheck, restart policy, and shutdown expectations.

## Phase 3: Feedback Persistence and Metrics

1. Wire the feedback consumer into the production runtime as a service.
2. Ensure feedback persistence is counted from actual DuckDB writes.
3. Produce a machine-readable continuous report contract with non-null
   lifecycle counters.

## Phase 4: Continuous Runtime Wiring

1. Define the continuous Nautilus runtime config in `nautilus_dev`.
2. Replace placeholder continuous counters with real runtime counters.
3. Verify real `rektslug` signals are consumed and feedback is published.

## Phase 5: Recovery and Fail-Closed Behavior

1. Define restart-safe expectations for the Nautilus service.
2. Define restart-safe expectations for the feedback consumer.
3. Verify residual position/order cleanup behavior.
4. Verify degraded paths fail closed: Redis unavailable, DuckDB unavailable,
   venue/API unavailable, feedback publish/persist mismatch.

## Phase 6: G3 Evidence and Review Package

1. Produce a real continuous paper/testnet run with non-placeholder counters.
2. Produce a machine-readable summary that proves lifecycle closure.
3. Update runbooks and execution-readiness docs with the frozen service model.
4. Mark the spec complete only when G3 is evidenced with concrete outputs.
