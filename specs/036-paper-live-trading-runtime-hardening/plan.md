# Plan: Paper/Live Trading Runtime Hardening (spec-036)

## Phase 1: Runtime Contract Freeze

1. Freeze runtime modes and promotion policy
2. Freeze required risk controls and kill-switch semantics
3. Freeze audit and observability requirements

## Phase 2: Signal Safety Layer

1. Define signal freshness and idempotency contract
2. Define duplicate prevention and stale-signal rejection
3. Define state persistence for in-flight execution decisions

## Phase 3: Risk and Recovery

1. Implement risk-policy enforcement boundaries
2. Implement restart-safe state recovery
3. Validate fail-closed behavior under degraded conditions

## Phase 4: Paper and Limited Live Rollout

1. Define paper deployment acceptance criteria
2. Define limited-live rollout criteria
3. Freeze evidence package required before full-live promotion

## Phase 5: External Review Handoff

1. Produce paper/live runtime checklist
2. Produce audit examples for executed and rejected actions
3. Produce rollback and incident handling notes
