# Rollout and Review: Runtime Hardening

## Paper Deployment Acceptance Checklist
- Runtime mode fixed to `paper` and verified at startup.
- Redis signal connectivity verified or explicit degraded-mode acceptance recorded.
- Risk policy pinned and persisted with restart recovery coverage.
- Signal freshness and duplicate rejection verified with test coverage.
- Audit trail persistence verified using `samples/runtime_state_example.json`.
- `/signals/status` verified to read measured 24h counts, not estimated placeholders.

## Limited-Live Rollout Checklist
- Execution mode promoted from `paper` to `live_limited` only after paper soak review.
- Allowlisted symbols and venues reduced to the minimum live scope.
- Max position size and daily loss limits tightened relative to paper mode.
- Kill-switch procedure tested and access path documented.
- Operator supervision window defined for the first live session.
- Rollback path to `paper` documented and rehearsed.

## Rollback Checklist
- Stop signal ingestion or disable execution promotion.
- Enable kill switch before changing any runtime policy.
- Persist current executor state and archive audit log.
- Revert runtime mode to `paper` and restore last known-good risk policy.
- Verify duplicate-signal rejection still holds after restart.
- Recheck `/signals/status` and audit log continuity before resuming.
