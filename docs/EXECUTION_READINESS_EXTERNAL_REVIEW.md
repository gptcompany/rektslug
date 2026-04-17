# External Review Summary: Execution Readiness Program

Date: 2026-04-17

## What This Review Covers

This review package covers the proposed work needed to move the repo from its
current public `liq-map` and artifact-serving baseline into:

- deterministic historical replay where currently missing
- execution-grade event-driven backtesting
- controlled paper trading
- constrained live trading

## What Was Added

- roadmap document: [docs/EXECUTION_READINESS_ROADMAP.md](./EXECUTION_READINESS_ROADMAP.md)
- proposed spec: `034-bybit-historical-producer-bridge`
- proposed spec: `035-nautilus-event-driven-backtest-hardening`
- proposed spec: `036-paper-live-trading-runtime-hardening`

## Existing Tracks Reused

- `spec-027`: Hyperliquid reserved-margin and portfolio-margin hardening
- `spec-015`: signal-loop infrastructure and downstream integration contract
- `spec-025`: WebSocket / event distribution backlog

## Program Recommendation

Recommended sequencing:

1. close correctness and historical-producer gaps first
2. harden event delivery and execution-grade backtesting second
3. only then promote to paper/live runtime hardening

## Main Design Decisions

- do not treat source-data existence as equivalent to producer-readiness
- keep event-driven backtest hardening separate from paper/live trading hardening
- keep runtime safety controls explicit and reviewable before live deployment
- preserve manifest-first and provenance-first design across all new work

## Questions For External Reviewers

1. Is `spec-034` correctly placed before execution work, or should it run in parallel?
2. Should `spec-035` and `spec-036` remain separate, or be merged?
3. Is WebSocket/event distribution truly on the critical path for execution, or
   can Redis-based downstream integration suffice initially?
4. Are the proposed live-trading runtime controls strong enough for a first
   limited rollout?
