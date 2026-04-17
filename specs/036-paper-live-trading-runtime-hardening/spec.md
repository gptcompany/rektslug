# Feature Specification: Paper/Live Trading Runtime Hardening

**Feature Branch**: `036-paper-live-trading-runtime-hardening`
**Created**: 2026-04-17
**Status**: Implemented
**Input**: Define the runtime contract that must exist before `rektslug`-driven
signals or strategies are allowed to progress from backtests into paper or live trading
**Dependencies**: spec-015 (signals), spec-025 (event distribution), spec-027
(margin correctness), spec-035 (execution-grade backtest)

## Context

The repo already contains several building blocks that are relevant to execution:

- signal publication and feedback ingestion
- monitoring endpoints for signals
- a Nautilus strategy bridge
- public API surfaces that downstream systems can consume

What does not yet exist is a hardened runtime contract covering:

- strategy enable/disable semantics
- risk limits and kill switches
- signal idempotency and stale-signal handling
- paper/live environment separation
- restart recovery and audit trails

Without that layer, paper or live trading would still rely on ad hoc operational
discipline rather than a repo-defined runtime boundary.

## Goal

Define and implement the runtime hardening required to move from event-driven
backtest outputs to controlled paper trading, and only then to constrained live
trading.

## Scope

### In Scope

- define runtime safety controls for paper and live execution
- define signal freshness, idempotency, and replay protection rules
- define audit and observability requirements for execution actions
- define environment separation between backtest, paper, and live modes
- define rollout gates from paper to live

### Out of Scope

- exchange-specific brokerage integrations beyond the runtime contract needed to
  host them safely
- alpha research or strategy optimization
- UI redesign

## Requirements

### Functional Requirements

- **FR-001**: The runtime MUST define explicit execution modes:
  - `backtest`
  - `paper`
  - `live_limited`
  - `live_full`
- **FR-002**: The runtime MUST enforce kill-switch and strategy-disable controls
  that do not depend on manual code edits.
- **FR-003**: Every execution action MUST be auditable with signal id,
  strategy id, input timestamp, action timestamp, and outcome.
- **FR-004**: The runtime MUST reject stale, duplicate, or mode-incompatible signals.
- **FR-005**: The runtime MUST enforce risk controls for:
  - max position size
  - max daily loss
  - max concurrent positions
  - venue / symbol allowlists
- **FR-006**: The runtime MUST recover safely across restart boundaries without
  losing execution state or duplicating actions.
- **FR-007**: Paper and live environments MUST remain configuration-isolated and
  operationally distinguishable.

### Non-Functional Requirements

- **NFR-001**: Runtime status metrics SHOULD reflect real counts, not estimates.
- **NFR-002**: All execution-critical state SHOULD be durable across process restart.
- **NFR-003**: Promotion from paper to live SHOULD require explicit gate review
  based on retained evidence, not operator memory.

## Success Criteria

- **SC-001**: A paper trading deployment can run with explicit mode, kill-switch,
  audit, and restart semantics.
- **SC-002**: A limited live deployment can be enabled without changing code and
  can be disabled immediately by runtime control.
- **SC-003**: External reviewers can reconstruct why each execution action did or
  did not happen from retained logs and state.
