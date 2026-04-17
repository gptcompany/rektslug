# Execution Readiness Roadmap

Date: 2026-04-17

## Purpose

This roadmap translates the current repo state into an execution-readiness
program for:

- deterministic multi-exchange artifact production
- event-driven strategy backtesting
- paper trading
- controlled live trading

It does not replace the current active liq-map scope. It organizes the next
delivery tracks once the current public liq-map baseline is considered stable
enough to support downstream execution work.

## Current Baseline

The repo is strongest today in:

- Binance-first public `liq-map` serving
- modeled snapshot artifact contracts
- provider-parity measurement for the public route
- signal-loop infrastructure (Redis pub/sub, feedback persistence, metrics API)

The repo is not yet execution-complete because the following gaps remain:

- historical-only Bybit windows are not producer-readable inside `rektslug`
- Hyperliquid reserved-margin / portfolio-margin work still needs formal closeout
- WebSocket / event distribution remains an explicit backlog track
- Nautilus support exists, but still as a bridge/demo path rather than a
  production-grade execution harness
- paper/live runtime controls are not yet formalized as a trading runtime contract

## Recommended Workstream Set

| Track | Type | Purpose | Status |
|------|------|---------|--------|
| `spec-027` | Existing | Hyperliquid reserved-margin and portfolio-margin hardening | Active backlog |
| `spec-015` phase 5 | Existing | Redis signal-loop integration with Nautilus/UTXOracle | Partially implemented, external integration open |
| `spec-025` | Existing | WebSocket and event distribution for real-time delivery | Open backlog |
| `spec-034` | New | Bybit historical producer bridge for 3TB-WDC historical windows | Proposed |
| `spec-035` | New | Execution-grade Nautilus event-driven backtest harness | Proposed |
| `spec-036` | New | Paper/live trading runtime hardening and operational controls | Proposed |

## Delivery Sequence

### Wave 1 - Data and Margin Correctness

1. Close `spec-027`
2. Implement `spec-034`

Rationale:

- margin correctness is a prerequisite for trustworthy Hyperliquid risk surfaces
- Bybit historical normalization is required before claiming deterministic
  historical replay coverage beyond live `ccxt-data-pipeline` windows

### Wave 2 - Event Delivery and Execution Research

3. Complete `spec-025`
4. Extend `spec-015` through external Nautilus integration
5. Implement `spec-035`

Rationale:

- delivery semantics should be explicit before wiring execution consumers
- the signal loop exists, but downstream consumption is still mostly a contract,
  not a closed execution path
- backtesting must move from demo support to a reproducible, execution-grade harness

### Wave 3 - Trading Runtime Hardening

6. Implement `spec-036`

Rationale:

- paper/live trading should start only after deterministic artifacts, signal
  delivery, and event-driven backtest behavior are all under control

## Exit Criteria By Stage

### Stage A - Historical Producer Readiness

- Bybit historical-only windows can produce deterministic artifacts from normalized
  local inputs
- no `blocked_source_unverified` status remains for windows covered by normalized
  historical data

### Stage B - Execution Backtest Readiness

- Nautilus backtests are replayable from manifest-addressed artifacts and pinned
  market data
- fills, fees, slippage, funding, and order-state assumptions are explicit
- backtest results can be reproduced from a retained manifest + config bundle

### Stage C - Paper Trading Readiness

- signal emission, consumer ingestion, and order decisions are fully observable
- order lifecycle, rejects, cancels, stale-signal handling, and kill-switch
  semantics are defined
- runtime metrics reflect real counts, not estimates

### Stage D - Live Trading Readiness

- hard risk limits exist at strategy, venue, and runtime layers
- all execution actions are auditable and recoverable after restart
- rollout policy supports dry-run -> paper -> limited live -> full live progression

## Relationship To Current Scope

`CURRENT_SCOPE.md` remains correct:

- the active default workstream is still public `liq-map`
- this roadmap is the next-stage execution program, not a change to the current
  default implementation target

## Review Questions

External reviewers should focus on:

1. Is the sequence correct, or should WebSocket/event distribution move later?
2. Should `spec-035` and `spec-036` remain separate, or be merged into one
   execution program spec?
3. Is Bybit historical normalization important enough to keep in the critical
   path, or should it be parallelized behind Binance/Hyperliquid execution work?
