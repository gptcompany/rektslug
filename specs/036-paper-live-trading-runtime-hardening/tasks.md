# Tasks: spec-036 Paper/Live Trading Runtime Hardening

## Phase 1: Runtime Contract

- [ ] T001 Freeze runtime mode taxonomy and promotion gates
- [ ] T002 Freeze risk-control requirements and kill-switch semantics
- [ ] T003 Freeze execution audit schema and recovery requirements

## Phase 2: Signal Safety

- [ ] T004R RED: Add failing tests for stale-signal and duplicate-signal rejection
- [ ] T005 Implement signal freshness and idempotency policy
- [ ] T006 Persist execution-critical identifiers and mode metadata

## Phase 3: Risk Controls

- [ ] T007R RED: Add failing tests for hard risk-limit enforcement
- [ ] T008 Implement risk-policy enforcement for size, loss, concurrency, and allowlists
- [ ] T009 Implement kill-switch / strategy-disable runtime controls

## Phase 4: Recovery and Audit

- [ ] T010R RED: Add failing tests for restart-safe recovery and no duplicate actions
- [ ] T011 Implement durable execution state and recovery flow
- [ ] T012 Implement audit artifact generation for executed, rejected, and canceled actions
- [ ] T013 Replace estimated runtime counters with real persisted or measured metrics

## Phase 5: Rollout and Review

- [ ] T014 Define paper deployment acceptance checklist
- [ ] T015 Define limited-live rollout checklist
- [ ] T016 Produce external review evidence package and rollback checklist
