# Evidence Package: spec-036 Paper/Live Trading Runtime Hardening

## Evidence Included
- `tests/test_runtime_hardening.py`: stale-signal, duplicate-signal, risk-limit, audit, and restart recovery coverage.
- `tests/unit/test_signal_publisher.py`: persisted publish metrics coverage.
- `tests/contract/test_signal_endpoints.py`: measured `/signals/status` counter coverage.
- `samples/runtime_state_example.json`: retained executor state with audit trail and persisted policy.
- `rollout.md`: paper, limited-live, and rollback checklists.

## Acceptance Mapping
- T013: measured signal status counters are now persisted/read from Redis-backed status store.
- T014: paper deployment checklist defined in `rollout.md`.
- T015: limited-live rollout checklist defined in `rollout.md`.
- T016: evidence package and rollback checklist delivered in this directory.
