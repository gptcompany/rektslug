# Feature Specification: Nautilus Liquidation Bridge Operational Closeout

**Feature Branch**: `037-nautilus-liquidation-bridge-operational-closeout`
**Created**: 2026-04-19
**Status**: Draft
**Input**: Close the operational loop from `rektslug` liquidation signals to a
Nautilus runtime that can consume, execute on testnet/paper, publish feedback,
recover safely, and produce reviewable evidence before any limited-live step.
**Dependencies**: spec-015 (signals), spec-035 (event-driven replay),
spec-036 (runtime hardening), `nautilus_dev` liquidation bridge commits
`3e3b97e`, `5f59d5e`, `6baf38e`

## Context

The execution loop has now been proven with real Hyperliquid testnet orders:

`rektslug signal -> Redis -> Nautilus bridge -> Hyperliquid testnet -> Redis feedback -> rektslug DuckDB`

Verified evidence already exists:

- guarded single-cycle smoke: `NODE_SMOKE_OK`
- sequential testnet soak: `2/2` cycles passed
- final account state after soak: `open_positions=0`, `open_orders=0`
- feedback persisted for each cycle into DuckDB

That is enough to show the bridge contract works. It is not enough to promote
the system to production live trading. The remaining gap is operational
closeout: longer soak, real-signal paper/testnet running, failure injection,
metrics, and explicit promotion gates.

## Goal

Promote the liquidation bridge from "testnet smoke passed" to a reviewed
paper/testnet operational candidate with enough retained evidence to decide
whether a future limited-live gate is safe.

## Scope

### In Scope

- extend the guarded testnet soak from short proof to reviewable operational run
- run continuous paper/testnet consumption of real `rektslug` signals
- track every signal lifecycle through accepted/rejected/submitted/filled/closed/feedback states
- verify restart and recovery behavior under controlled failure points
- aggregate operational metrics into machine-readable evidence
- define promotion gates from dry-run to testnet soak to paper/testnet continuous
- produce final evidence package for external review

### Out of Scope

- mainnet trading enablement
- alpha research or probability calibration for liquidation signals
- reserved-margin / portfolio-margin solver work from `spec-027`
- generic WebSocket/event distribution backlog from `spec-011` / `spec-025`
- broad UI work

## Runtime Boundary

This spec spans two repositories:

- `rektslug`: signal production, Redis contract, feedback ingestion, DuckDB
  persistence, runbooks, evidence package
- `nautilus_dev`: Nautilus live/testnet strategy, guarded smoke/soak scripts,
  order lifecycle, recovery behavior

Any implementation must preserve small reviewable commits and must not mix
unrelated worktree changes into this spec.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST retain a guarded testnet smoke command that refuses
  to place orders without an explicit confirmation flag.
- **FR-002**: The system MUST support a sequential testnet soak command that runs
  `N` guarded cycles and writes per-cycle and aggregate JSON results.
- **FR-003**: Every soak cycle MUST assert:
  - one signal was submitted
  - one position was opened
  - one position was closed
  - one feedback row was persisted
  - final open positions are zero
  - final open orders are zero
- **FR-004**: The system MUST support a paper/testnet continuous mode that
  consumes real `rektslug` signals rather than only synthetic smoke signals.
- **FR-005**: The system MUST track signal lifecycle state at minimum:
  `received`, `rejected`, `accepted`, `order_submitted`, `order_rejected`,
  `filled`, `position_opened`, `position_closed`, `feedback_published`,
  `feedback_persisted`.
- **FR-006**: The system MUST expose machine-readable metrics for signal,
  execution, feedback, and cleanup outcomes.
- **FR-007**: The system MUST define and test recovery behavior for controlled
  process interruption before and after order/position/feedback boundaries.
- **FR-008**: The system MUST fail closed when Redis feedback, DuckDB persistence,
  or account cleanup verification fails.
- **FR-009**: The system MUST produce a final evidence package with commands,
  commit hashes, JSON reports, failure-injection results, and residual risks.

### Non-Functional Requirements

- **NFR-001**: Secrets MUST be supplied via environment or dotenvx and MUST NOT
  be printed in logs, reports, or runbooks.
- **NFR-002**: Operational evidence SHOULD be reproducible without relying on
  operator memory or terminal scrollback.
- **NFR-003**: The soak and continuous runners SHOULD prefer explicit JSON output
  over parsing human-readable logs.
- **NFR-004**: Recovery tests SHOULD leave the venue account flat and with no
  open orders, even when the tested failure path is expected to fail the run.
- **NFR-005**: Review artifacts SHOULD distinguish exchange/testnet failures from
  bridge logic failures.

## Success Criteria

- **SC-001**: A long soak run completes the configured number of cycles with
  `feedback_rows=1`, `open_positions=0`, and `open_orders=0` for every cycle.
- **SC-002**: A continuous paper/testnet run consumes real `rektslug` signals for
  the configured window and produces a complete lifecycle report.
- **SC-003**: Recovery tests pass for restart/failure points covering:
  pre-submit, post-submit/pre-fill, open-position/pre-close, post-close/pre-feedback,
  Redis unavailable, and DuckDB unavailable.
- **SC-004**: The evidence package is sufficient for an external reviewer to
  reconstruct what ran, what passed, what failed, and what remains blocked.
- **SC-005**: Promotion beyond testnet/paper remains blocked unless all gates are
  satisfied and explicitly approved in a later spec or rollout document.

## Promotion Gates

| Gate | Purpose | Exit Condition |
|------|---------|----------------|
| `G0` dry-run | no venue orders | real-signal lifecycle decisions recorded without execution |
| `G1` smoke | one guarded testnet cycle | `NODE_SMOKE_OK`, flat account, one feedback row |
| `G2` soak | repeated guarded testnet cycles | all cycles pass, aggregate JSON retained |
| `G3` continuous paper/testnet | real signal consumption | defined runtime window passes with no residual exposure |
| `G4` external review | independent review | evidence package accepted with residual risks listed |

`G5` limited live is intentionally out of scope for this spec.

## Risks And Constraints

- Hyperliquid testnet availability can create false negatives; evidence must
  label infra/venue failures separately from bridge failures.
- Real `rektslug` signals may be sparse; continuous mode needs an explicit
  runtime window and a minimum-event policy.
- Nautilus native runtime requires Python 3.12+.
- Existing repo worktrees may contain unrelated dirty files; implementation
  commits must stage only spec-related files.
