# Tasks: spec-038 Circuit Breaker + Shadow Mode

## Phase 1: Circuit Breaker Core (TDD)

- [ ] T001 Write failing tests for circuit breaker logic (TDD RED):
  consecutive losses, session drawdown, rate limit, sliding window,
  manual reset, auto-reset cooldown, cooldown=0, win resets streak,
  persist callback
- [ ] T002 Implement CircuitBreakerConfig, TripReason, CircuitBreaker (TDD GREEN)
- [ ] T003 Verify all tests pass, refactor if needed (TDD REFACTOR)

## Phase 2: Persistence + API + Consumer Wiring

- [ ] T004 Write failing tests for CircuitBreakerStore DuckDB persistence (TDD RED)
- [ ] T005 Implement CircuitBreakerStore with save/load state (TDD GREEN)
- [ ] T006 Add GET /signals/circuit-breaker endpoint to signals router
- [ ] T007 Integrate CB gate into continuous_consumer.py with CLI args
- [ ] T008 Wire Redis alert callback on trip

## Phase 3: Shadow Mode

- [ ] T009 Write failing tests for ShadowTracker hypothetical PnL (TDD RED)
- [ ] T010 Implement ShadowTracker + CalibrationSummary (TDD GREEN)
- [ ] T011 Extend continuous_consumer.py with --shadow-mode and --report-interval-secs
- [ ] T012 Add SIGTERM/SIGINT graceful shutdown with final report
- [ ] T013 Add calibration summary generation at shutdown

## Phase 4: E2E Verification + Docs

- [ ] T014 Smoke test: shadow mode 10+ min against live Redis
- [ ] T015 Verify CB state persists across process restart
- [ ] T016 Verify API endpoint and Redis alert on trip
- [ ] T017 Update docs/ARCHITECTURE.md with CB + shadow subsystem
- [ ] T018 Final secret scan on all new files
