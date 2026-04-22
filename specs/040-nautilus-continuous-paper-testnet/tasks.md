# Tasks: spec-040 Nautilus Continuous Paper/Testnet Runtime

## Phase 1: Contract Freeze

- [ ] T001 Freeze multi-repo ownership boundaries for `rektslug` and `nautilus_dev`
- [x] T002 Freeze the first deployment shape:
  `systemd-separated Nautilus service` or `cross-repo compose service`
- [ ] T003 Freeze required lifecycle states and mandatory counters for G3
- [ ] T004 Freeze fail-closed conditions for execution, feedback, and cleanup
- [ ] T005 Freeze continuous-mode evidence schema and report locations

Phase-1 note:
- T003-T005 are the remaining analysis tasks before implementation should start.

## Phase 2: Service Topology

- [ ] T006 Define the `nautilus-liquidation-paper-testnet` service contract in
  `nautilus_dev`
- [x] T007 Define the `rektslug-feedback-consumer` service contract in `rektslug`
- [ ] T008 Freeze secret handling for `HYPERLIQUID_TESTNET_PK` using dotenvx/env
- [ ] T009 Freeze restart policy, shutdown behavior, and healthcheck semantics
- [x] T009B Implement and test paper/testnet mode separation: service must
  fail-closed if configured mode is inconsistent with venue/environment
  (covers FR-006)
- [ ] T010 Document the final runtime topology in runbook form

Phase-2 note:
- `rektslug-feedback-consumer` is frozen as a separate service, not an
  extension of `rektslug-shadow-consumer`.
- `rektslug-feedback-consumer` is frozen as a compose-managed `rektslug`
  service, not a separate host systemd unit.

## Phase 3: Feedback Persistence and Metrics

- [x] T011R RED: write failing tests for always-on feedback consumption and
  persistence accounting in `rektslug`
- [x] T012 Wire the feedback consumer into the production runtime as a service,
  not just a module/CLI
- [x] T013R RED: write failing test asserting continuous metrics return measured
  values (not placeholders) from actual runtime counters
- [x] T013 Replace placeholder continuous metrics with measured runtime counters
- [x] T014 Ensure `feedback_persisted` is counted from actual DuckDB writes, not
  inferred from logs
- [x] T015 Produce a machine-readable continuous report contract with non-null
  lifecycle counters

Phase-3 intent:
- this phase closes the current factual gap where the repo has feedback code but
  not an always-on feedback-persistence service in the production runtime

## Phase 4: Continuous Runtime Wiring

- [x] T016 Define the continuous Nautilus runtime config:
  mode, symbol allowlist, confidence floor, max size, max concurrent exposure,
  max runtime window, Redis endpoint, feedback contract
- [x] T017R RED: write failing tests or acceptance checks for real runtime
  counters replacing the current placeholder values
- [x] T018R RED: write integration test asserting the continuous service
  consumes a signal from Redis and publishes feedback within timeout
- [x] T018 Implement or wire the long-running paper/testnet service in
  `nautilus_dev`
- [x] T019 Verify that real `rektslug` signals are consumed without manual
  injection
- [x] T020 Verify that every accepted execution path can publish feedback back
  into `rektslug`

## Phase 5: Recovery and Fail-Closed Behavior

- [x] T021 Define restart/recovery expectations for the Nautilus service
- [x] T022 Define restart/recovery expectations for the feedback consumer
- [x] T023 Verify Redis-unavailable behavior fails closed
- [x] T024 Verify DuckDB-unavailable behavior fails closed
- [x] T025 Verify residual open positions/open orders are explicitly checked and
  reported after restart or shutdown
- [x] T026 Verify feedback publish/persist mismatches are visible and block a
  green result
- [x] T026B Verify feedback consumer and DuckDB writes do not block the
  Nautilus event loop (NFR-002): measure round-trip latency under load,
  confirm async boundary at Redis

## Phase 6: Evidence and Review

- [ ] T027 Run a continuous paper/testnet session with real `rektslug` signals
- [ ] T028 Retain a report showing non-placeholder counters:
  `signals_seen`, `accepted`, `orders_submitted`, `positions_opened`,
  `positions_closed`, `feedback_published`, `feedback_persisted`
- [x] T029 Reconcile the continuous report against DuckDB `signal_feedback` rows
  and service logs
- [x] T030 Update `docs/EXECUTION_READINESS_ROADMAP.md` with the spec-040 result
- [x] T031 Update `docs/EXECUTION_READINESS_EXTERNAL_REVIEW.md` with reviewer
  entry points for the continuous runtime
- [x] T031B Document public interfaces: feedback consumer Redis contract,
  continuous report JSON schema, and healthcheck endpoints in
  `docs/ARCHITECTURE.md` or dedicated doc
- [ ] T032 Final review: confirm no secrets leak into logs, runbooks, reports,
  or committed artifacts

Phase-6 note:
- T027 and T028 remain operational gates and require a retained real session.
- T029-T031 can be implemented and reviewed before the real G3 session exists.
