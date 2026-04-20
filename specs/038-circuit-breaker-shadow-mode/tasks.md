# Tasks: spec-038 Circuit Breaker + Shadow Mode

## Phase 1: Circuit Breaker Core (TDD)

- [x] T001 Write failing tests for circuit breaker logic (TDD RED):
  consecutive losses, session drawdown, rate limit, sliding window,
  manual reset, auto-reset cooldown, cooldown=0, win resets streak,
  persist callback
- [x] T002 Implement CircuitBreakerConfig, TripReason, CircuitBreaker (TDD GREEN)
- [x] T003 Verify all tests pass, refactor if needed (TDD REFACTOR)

## Phase 2: Persistence + API + Consumer Wiring

- [x] T004 Write failing tests for CircuitBreakerStore DuckDB persistence (TDD RED)
- [x] T005 Implement CircuitBreakerStore with save/load state (TDD GREEN)
- [x] T006 Add GET /signals/circuit-breaker endpoint to signals router
- [x] T007 Integrate CB gate into continuous_consumer.py with CLI args
- [x] T008 Wire Redis alert callback on trip

## Phase 3: Shadow Mode

- [x] T009 Write failing tests for ShadowTracker hypothetical PnL (TDD RED)
- [x] T010 Implement ShadowTracker + CalibrationSummary (TDD GREEN)
- [x] T011 Extend continuous_consumer.py with --shadow-mode and --report-interval-secs
- [x] T012 Add SIGTERM/SIGINT graceful shutdown with final report
- [x] T013 Add calibration summary generation at shutdown

## Phase 4: E2E Verification + Docs

- [x] T014 Smoke test: 3 synthetic signals consumed, report written, CB state correct
- [x] T015 Verify CB state persists across process restart (in-memory round-trip)
- [x] T016 Verify Redis alert published on circuit breaker trip
- [x] T017 Update docs/ARCHITECTURE.md with CB + shadow subsystem
- [x] T018 Final secret scan on all new files
