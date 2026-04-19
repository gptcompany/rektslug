# Plan: Circuit Breaker + Shadow Mode (spec-038)

## Architecture

### Component Ownership

| Component | Key Files |
|-----------|-----------|
| Circuit breaker logic + store | `src/liquidationheatmap/signals/circuit_breaker.py` |
| Shadow tracker + calibration | `src/liquidationheatmap/signals/shadow.py` |
| API endpoint | `src/liquidationheatmap/api/routers/signals.py` |
| Consumer integration | `scripts/continuous_consumer.py` |

### Data Flow

```
Signal arrives on Redis
  -> continuous_consumer receives
  -> CircuitBreaker.check(symbol)
     -> if tripped: REJECT with reason "circuit_breaker:{type}"
     -> if allowed: proceed to accept/execute
  -> on feedback: CircuitBreaker.record_outcome(symbol, pnl)
  -> on trip: publish alert to liquidation:alerts:{symbol}

Shadow mode (dry-run):
  -> ShadowTracker records hypothetical entry
  -> next signal approximates exit price
  -> hypothetical PnL feeds CircuitBreaker.record_outcome()
  -> periodic report + calibration summary at shutdown
```

### DuckDB Schema Addition

```sql
CREATE TABLE IF NOT EXISTS circuit_breaker_state (
  symbol VARCHAR PRIMARY KEY,
  consecutive_losses INT NOT NULL DEFAULT 0,
  session_pnl DOUBLE NOT NULL DEFAULT 0.0,
  tripped BOOLEAN NOT NULL DEFAULT FALSE,
  trip_reason VARCHAR,
  tripped_at TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

### Inter-Phase Dependencies

- Phase 2 depends on Phase 1 (core logic must exist before wiring)
- Phase 3 depends on Phase 2 (shadow feeds CB via record_outcome)
- Phase 4 depends on Phase 3 (E2E verification of complete flow)

## Phase 1: Circuit Breaker Core (TDD)

1. Write failing tests for all circuit breaker conditions.
2. Implement pure-logic CircuitBreaker class with zero external deps.
3. Cover: consecutive losses, session drawdown, rate limit, reset, cooldown.

## Phase 2: Persistence + API + Consumer Wiring

1. Add CircuitBreakerStore with DuckDB persistence.
2. Add GET /signals/circuit-breaker API endpoint.
3. Integrate CB gate into continuous_consumer.py.
4. Wire Redis alert on trip via callback.

## Phase 3: Shadow Mode

1. Implement ShadowTracker with hypothetical PnL.
2. Extend continuous_consumer.py with --shadow-mode, periodic reports, SIGTERM.
3. Add calibration summary at shutdown.

## Phase 4: E2E Verification + Docs

1. Smoke test shadow mode against live Redis.
2. Verify CB persistence across restart.
3. Verify API and Redis alerts.
4. Update docs/ARCHITECTURE.md.
