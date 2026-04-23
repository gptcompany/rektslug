# Feature Specification: Nautilus Continuous Paper/Testnet Runtime

**Feature Branch**: `040-nautilus-continuous-paper-testnet`
**Created**: 2026-04-21
**Status**: Implemented with retained G3 evidence
**Input**: Close the remaining execution gap after the production `rektslug`
signal/shadow/backfill runtime by defining a continuous paper/testnet runtime
that can consume real `rektslug` signals, execute through Nautilus, persist
feedback, recover safely, and produce reviewable evidence.
**Dependencies**: spec-015 (signals), spec-036 (paper/live runtime hardening),
spec-037 (bridge operational closeout), `nautilus_dev` guarded bridge/runtime,
official NautilusTrader nightly documentation.

## Context

`rektslug` is now production-enabled for:

- API serving
- market-data sync
- Hyperliquid shadow validation
- historical backfill
- automated monitoring

The execution gap is narrower and more concrete than before:

- `rektslug` already produces real signals and persists runtime state.
- `nautilus_dev` already proved the guarded testnet smoke/soak loop.
- `rektslug` already contains Redis feedback models and DuckDB persistence code.

What does **not** exist yet as a production runtime:

- no continuous Nautilus execution service in the live stack
- no always-on feedback consumer attached to the `rektslug` runtime
- no unified G3 report with non-placeholder execution metrics
- no restart-safe, service-grade continuous paper/testnet loop

Current facts:

- `docker-compose.yml` contains `rektslug-api`, `rektslug-sync`, `redis`,
  `rektslug-shadow-producer`, and `rektslug-shadow-consumer`, but no Nautilus
  continuous execution service
- `scripts/continuous_testnet.py` is a bounded wrapper, not a production
  service, and still writes placeholder counters
- `src/liquidationheatmap/signals/feedback.py` exists, but is not wired into the
  current compose/systemd runtime as an always-on consumer

The remaining gap is not signal generation. It is execution wiring, feedback
persistence as a service, and continuous-runtime hardening.

## Goal

Define a service-grade continuous paper/testnet runtime which closes this loop
with measurable, restart-safe behavior:

`rektslug signal -> Redis -> Nautilus execution -> Redis feedback -> rektslug DuckDB/reporting`

The output of this spec is a reviewed operational design and acceptance
contract for `G3 continuous paper/testnet`, not limited-live or mainnet
enablement.

## Runtime Boundary

This spec spans two repositories and must preserve that boundary.

- `rektslug` owns:
  - signal production
  - Redis signal/feedback contracts
  - feedback persistence into DuckDB
  - reporting, monitoring, and circuit breaker integration
  - production runbooks/evidence package
- `nautilus_dev` owns:
  - Nautilus runtime process
  - venue connectivity
  - order lifecycle
  - execution reconciliation
  - paper/testnet strategy process and restart behavior

This spec must not pretend that `rektslug` alone owns the execution runtime.

## Frozen Decision

The first iteration will use a `systemd-separated Nautilus service`.

That means:

- `rektslug` remains the production signal/reporting runtime in this repo
- `nautilus_dev` owns the long-running Nautilus paper/testnet execution service
- Redis remains the shared integration boundary
- `rektslug` adds an always-on feedback consumer on its own side

`cross-repo compose service` remains a possible future packaging choice, but it
is not the accepted starting point for spec-040.

The `rektslug-feedback-consumer` will also be a separate service. It will not
be attached to `rektslug-shadow-consumer` in the first iteration.
It will run in `rektslug` Docker Compose, not as a separate host systemd unit.

## Nautilus Nightly Constraints

The design must respect current official NautilusTrader nightly constraints:

- Python `3.12` to `3.14` is required for the supported runtime path
- `TradingNode` should run as a standalone Python script/service, not in Jupyter
- one `TradingNode` per process
- user code on the event loop must not block
- live execution relies on execution reconciliation inside the live execution
  engine

Primary sources:

- https://nautilustrader.io/docs/nightly/getting_started/
- https://nautilustrader.io/docs/nightly/concepts/live/
- https://nautilustrader.io/docs/nightly/how_to/configure_live_trading

These constraints strongly favor a dedicated Nautilus service process rather
than embedding execution inside an existing `rektslug` worker.

## Scope

### In Scope

- define the continuous paper/testnet runtime boundary between `rektslug` and
  `nautilus_dev`
- define the accepted deployment shape for a long-running Nautilus service
- define the always-on feedback-consumer requirement in `rektslug`
- define the metrics and lifecycle states required for G3 evidence
- define restart/recovery requirements for both the execution service and the
  feedback-persistence path
- define secret handling and mode separation for testnet/paper operation
- define the minimum runbook and evidence package for an operational review

### Out of Scope

- mainnet trading
- limited-live or full-live promotion
- alpha or signal-quality research
- HFT / low-latency execution optimization
- refactoring the Nautilus strategy logic itself
- replacing the shadow pipeline as the validation path

## Accepted Deployment Shape

### First Iteration Topology

- keep `rektslug` as the production signal/feedback/reporting service
- keep Nautilus continuous execution in `nautilus_dev`
- run Nautilus as its own long-running service, with Redis as the shared bus
- add an always-on feedback consumer to `rektslug` as its own service

Accepted packaging for the first iteration:

- separate systemd-managed `nautilus_dev` service with shared Redis
- `rektslug-feedback-consumer` managed in `rektslug` Docker Compose

Future alternative, explicitly out of the frozen decision:

- cross-repo compose orchestration where the Nautilus service still uses the
  `nautilus_dev` runtime image/config

Reason:

- aligns with the current ownership boundary
- avoids forcing the Nautilus 3.12 runtime into the `rektslug` core image
- matches Nautilus nightly guidance around standalone service processes
- reduces packaging risk while the runtime is still in paper/testnet mode
- keeps feedback persistence inside the existing `rektslug` deployment boundary

## Required Services

### rektslug

- existing:
  - `rektslug-api`
  - `rektslug-sync`
  - `redis`
  - `rektslug-shadow-producer`
  - `rektslug-shadow-consumer`
- new:
  - `rektslug-feedback-consumer` as a distinct service, not merged into
    `rektslug-shadow-consumer`

### nautilus_dev

- new:
  - `nautilus-liquidation-paper-testnet`

## Required Lifecycle States

The continuous runtime must track at minimum:

- `received`
- `rejected`
- `accepted`
- `order_submitted`
- `order_rejected`
- `order_filled`
- `position_opened`
- `position_closed`
- `feedback_published`
- `feedback_persisted`
- `cleanup_verified`

The runtime must not collapse these into a single success/fail counter.

## Minimum Runtime Outputs

At minimum, the continuous runtime must emit or make reconstructable:

- `signals_seen`
- `signals_rejected`
- `signals_accepted`
- `orders_submitted`
- `orders_rejected`
- `orders_filled`
- `positions_opened`
- `positions_closed`
- `feedback_published`
- `feedback_persisted`
- `residual_open_positions`
- `residual_open_orders`

## Functional Requirements

- **FR-001**: The system must run Nautilus continuous paper/testnet execution as
  a long-running service, not only as a bounded wrapper script.
- **FR-002**: The service must consume real `rektslug` Redis signals without
  requiring manual signal injection.
- **FR-003**: `rektslug` must run an always-on feedback consumer that subscribes
  to `liquidation:feedback:{symbol}` and persists feedback into DuckDB.
- **FR-004**: The runtime must produce machine-readable metrics for:
  - signals seen
  - signals accepted/rejected
  - orders submitted/rejected
  - positions opened/closed
  - feedback published/persisted
  - residual open positions/open orders
- **FR-005**: The runtime must persist enough state to recover safely across
  service restart without duplicating execution actions or silently losing
  feedback.
- **FR-006**: The runtime must support explicit paper/testnet mode separation and
  must fail closed if the configured mode is inconsistent.
- **FR-007**: Secret injection for `HYPERLIQUID_TESTNET_PK` must use the
  existing dotenvx/environment standards and must not leak into logs.
- **FR-008**: The final G3 evidence report must use real counters from runtime
  events, not placeholder values.

## Non-Functional Requirements

- **NFR-001**: The Nautilus service must remain one `TradingNode` per process.
- **NFR-002**: The design must not block the Nautilus event loop with heavy
  `rektslug`-side work such as DuckDB writes or reporting logic.
- **NFR-003**: Restart behavior should be reviewable from persisted state and
  logs, not operator memory.
- **NFR-004**: Feedback persistence failures must be visible and fail closed.
- **NFR-005**: The service topology should be operable on the workstation
  without forcing a full image/runtime merge between the two repos.

## Explicit Non-Claims

This spec does not claim any of the following:

- limited-live readiness
- mainnet readiness
- profitability
- low-latency edge
- replacement of the shadow pipeline as the validation gate

## Success Criteria

- **SC-001**: A continuous paper/testnet session runs as a service for a defined
  window and consumes real `rektslug` signals.
- **SC-002**: At least one end-to-end non-smoke signal completes the full path:
  `received -> accepted -> order/position lifecycle -> feedback_published -> feedback_persisted`.
- **SC-003**: Restarting the execution service does not leave hidden residual
  exposure or duplicate the same signal execution.
- **SC-004**: Restarting the feedback consumer does not silently lose feedback
  persistence.
- **SC-005**: The resulting G3 report contains non-placeholder counters and can
  be reconciled against DuckDB rows and service logs.

## Deliverables

- a continuous-runtime service design for `nautilus_dev`
- a `rektslug-feedback-consumer` service design
- a machine-readable G3 report contract
- systemd/compose/runbook decisions for how the two runtimes coexist
- an evidence package template for continuous paper/testnet runs

## Resolved Questions

1. Should the feedback consumer live in compose or systemd?
   **RESOLVED**: compose-managed service in `rektslug` Docker Compose
   (frozen).

## Open Questions

1. What is the minimum accepted runtime window for G3: time-based,
   signal-count-based, or both?
2. Is the first production-usable downstream mode `paper`, `testnet`, or a
   documented split where both exist but only one is promoted?
3. Which metrics are mandatory for promotion review beyond lifecycle counts:
   latency, PnL, residual exposure, recovery count, venue errors?
