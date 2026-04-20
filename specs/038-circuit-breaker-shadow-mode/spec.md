# Feature Specification: Circuit Breaker + Shadow Mode

**Feature Branch**: `038-circuit-breaker-shadow-mode`
**Created**: 2026-04-20
**Status**: Implemented
**Dependencies**: spec-037 (operational closeout), spec-015 (signals)

## Context

The liquidation bridge (spec-037) is operationally proven: 20/20 soak cycles,
6/6 fault injection tests, lifecycle tracking, and fail-closed behavior. However,
there is no runtime protection against sustained losses. If the bridge starts
losing consecutively or drawdown exceeds a threshold, it continues accepting
signals indefinitely.

Two complementary mechanisms close this gap:

1. **Circuit Breaker** stops accepting signals when conditions deteriorate.
2. **Shadow Mode** observes real signals for extended periods without executing,
   producing the data needed to calibrate circuit breaker thresholds.

Shadow mode produces the data. Circuit breaker consumes it.

## Goal

Add automatic signal rejection under adverse conditions and a long-running
observation mode that calibrates rejection thresholds from real market data.

## Scope

### In Scope

- circuit breaker with three trip conditions: consecutive losses, session
  drawdown, and hourly rate limit
- persistence of circuit breaker state across restarts
- API endpoint exposing circuit breaker status
- Redis alert on circuit breaker trip
- extended shadow mode for the continuous consumer (hours/days, not seconds)
- periodic JSON reporting during shadow observation
- hypothetical PnL tracking from shadow signals
- calibration summary suggesting circuit breaker thresholds

### Out of Scope

- mainnet trading enablement
- changes to the nautilus_dev repository
- alpha research or probability calibration
- UI dashboard for circuit breaker state
- automated threshold tuning (ML-based)

## Requirements

### Functional Requirements

- **FR-001**: The circuit breaker MUST reject signals after N consecutive losses
  (configurable, default 5).
- **FR-002**: The circuit breaker MUST reject signals when session cumulative PnL
  falls below a configurable threshold (default -50.0 USDT).
- **FR-003**: The circuit breaker MUST reject signals when accepted signals in the
  last hour exceed a configurable limit (default 10).
- **FR-004**: When tripped, the circuit breaker MUST log the reason and publish an
  alert to `liquidation:alerts:{symbol}`.
- **FR-005**: The circuit breaker MUST support manual reset and auto-reset after a
  configurable cooldown (default 300s, 0 = manual only).
- **FR-006**: Circuit breaker state MUST persist to DuckDB and recover on restart.
- **FR-007**: The API MUST expose circuit breaker status via
  `GET /signals/circuit-breaker?symbol=`.
- **FR-008**: Shadow mode MUST run the continuous consumer in dry-run for
  unbounded duration with graceful SIGTERM shutdown.
- **FR-009**: Shadow mode MUST produce periodic JSON reports at a configurable
  interval (default 300s).
- **FR-010**: Shadow mode MUST track hypothetical PnL for accepted signals using
  subsequent signal prices as exit proxy.
- **FR-011**: Shadow mode MUST produce a calibration summary at shutdown with
  suggested circuit breaker thresholds.

### Non-Functional Requirements

- **NFR-001**: Circuit breaker core logic MUST have zero external dependencies
  (no Redis, no DuckDB) for maximum testability.
- **NFR-002**: Circuit breaker MUST be injected into the continuous consumer via
  composition, not inheritance.
- **NFR-003**: Shadow mode MUST handle SIGTERM/SIGINT gracefully without data loss.
- **NFR-004**: Hypothetical PnL is intentionally coarse (signal price proxy) and
  MUST NOT be presented as backtesting.

## Success Criteria

- **SC-001**: Circuit breaker trips correctly for all three conditions with
  deterministic tests.
- **SC-002**: Circuit breaker state survives process restart via DuckDB.
- **SC-003**: Shadow mode runs for 10+ minutes, produces periodic reports, and
  generates a calibration summary at shutdown.
- **SC-004**: API endpoint returns correct circuit breaker state.
