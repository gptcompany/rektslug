# Execution Readiness Roadmap

Date: 2026-04-17

## Purpose

This roadmap tracks the execution-readiness program that sits behind the public
`liq-map` workstream:

- deterministic multi-exchange artifact production
- event-driven strategy backtesting
- paper trading
- controlled live trading

## Current Baseline

The repo is strongest today in:

- Binance-first public `liq-map` serving
- modeled snapshot artifact contracts
- provider-parity measurement for the public route
- signal-loop infrastructure (Redis pub/sub, feedback persistence, metrics API)
- retained Bybit historical bridge samples for producer-readable replay
- retained Nautilus replay bundles and machine-readable backtest result helpers
- runtime hardening with persisted signal status metrics and restart-safe executor state

The repo is not yet fully execution-complete because the following gaps remain:

- Hyperliquid reserved-margin / portfolio-margin work still needs formal closeout
- WebSocket / event distribution under `spec-011` remains a separate backlog track
- native Nautilus engine execution still requires a Python 3.12+ runtime when running the real engine, not the mocked test harness

## Workstream Status

| Track | Type | Purpose | Status |
|------|------|---------|--------|
| `spec-027` | Existing | Hyperliquid reserved-margin and portfolio-margin hardening | Active backlog |
| `spec-015` phase 5 | Existing | Redis signal-loop integration with Nautilus/UTXOracle | Partially implemented, external integration open |
| `spec-025` | Existing | WebSocket and event distribution for real-time delivery | Open backlog |
| `spec-034` | Follow-on | Bybit historical producer bridge for 3TB-WDC historical windows | Implemented and sample-validated |
| `spec-035` | Follow-on | Execution-grade Nautilus event-driven backtest harness | Implemented with retained replay bundles |
| `spec-036` | Follow-on | Paper/live trading runtime hardening and operational controls | Implemented with evidence package |
| `spec-037` | Follow-on | Nautilus liquidation bridge operational closeout | Implemented with multi-repo evidence |

## Delivered Sequence

### Wave 1 - Data and Margin Correctness

1. Close Python/runtime compatibility blockers affecting `spec-027` validation.
2. Implement `spec-034` with retained sample historical manifests and deterministic normalization coverage.

### Wave 2 - Event Delivery and Execution Research

3. Complete minimum viable WebSocket delivery wiring.
4. Extend `spec-015` through downstream Nautilus signal consumption.
5. Implement `spec-035` replay bundle/result hardening and retained review bundles.

### Wave 3 - Trading Runtime Hardening

6. Implement `spec-036` runtime persistence, measured signal status counters, and rollout/evidence docs.
7. Implement `spec-037` operational closeout for the Nautilus liquidation bridge with guarded soak evidence.

## Exit Criteria By Stage

### Stage A - Historical Producer Readiness

- Bybit historical-only windows can produce deterministic artifacts from normalized local inputs.
- no `blocked_source_unverified` status remains for windows covered by normalized historical data.
- retained sample manifests exist for `bybit_standard` and `depth_weighted`.

### Stage B - Execution Backtest Readiness

- Nautilus backtests are replayable from retained replay bundles and pinned market data references.
- fills, fees, slippage, funding, and order-state assumptions are explicit.
- machine-readable backtest results round-trip through export/load helpers.

### Stage C - Paper Trading Readiness

- signal emission, consumer ingestion, and order decisions are observable.
- order lifecycle, rejects, cancels, stale-signal handling, and kill-switch semantics are defined.
- runtime metrics reflect measured counts, not estimated placeholders.

### Stage D - Live Trading Readiness

- hard risk limits exist at strategy, venue, and runtime layers.
- all execution actions are auditable and recoverable after restart.
- rollout policy supports dry-run -> paper -> limited live -> full live progression.

## Relationship To Current Scope

`CURRENT_SCOPE.md` remains the active default for ambiguous requests:

- the default implementation target is still public `liq-map`
- this roadmap records the next-stage execution work that has now been implemented in follow-on tracks
- remaining backlog after these follow-ons is mainly `spec-027`, `spec-015` external integration, and `spec-011`/`spec-025` delivery scope
