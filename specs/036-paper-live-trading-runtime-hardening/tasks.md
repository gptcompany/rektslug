# Tasks: spec-036 Paper/Live Trading Runtime Hardening

## Phase 1: Runtime Contract

- [x] T001 Freeze runtime mode taxonomy and promotion gates
- [x] T002 Freeze risk-control requirements and kill-switch semantics
- [x] T003 Freeze execution audit schema and recovery requirements

## Phase 2: Signal Safety

- [x] T004R RED: Add failing tests for stale-signal and duplicate-signal rejection
- [x] T005 Implement signal freshness and idempotency policy
- [x] T006 Persist execution-critical identifiers and mode metadata

## Phase 3: Risk Controls

- [x] T007R RED: Add failing tests for hard risk-limit enforcement
- [x] T008 Implement risk-policy enforcement for size, loss, concurrency, and allowlists
- [x] T009 Implement kill-switch / strategy-disable runtime controls

## Phase 4: Recovery and Audit

- [x] T010R RED: Add failing tests for restart-safe recovery and no duplicate actions
- [x] T011 Implement durable execution state and recovery flow
- [x] T012 Implement audit artifact generation for executed, rejected, and canceled actions
- [x] T013 Replace estimated runtime counters with real persisted or measured metrics

## Phase 5: Rollout and Review

- [x] T014 Define paper deployment acceptance checklist
- [x] T015 Define limited-live rollout checklist
- [x] T016 Produce external review evidence package and rollback checklist
