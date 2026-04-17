# Feature Specification: Nautilus Event-Driven Backtest Hardening

**Feature Branch**: `035-nautilus-event-driven-backtest-hardening`
**Created**: 2026-04-17
**Status**: Proposed
**Input**: Promote the current Nautilus bridge from demo support to an
execution-grade, reproducible event-driven backtest harness
**Dependencies**: spec-015 (signals), spec-027 (margin correctness), spec-030
/ spec-034 (artifact provenance), ccxt-data-pipeline catalog, optional Nautilus
runtime environment

## Context

`rektslug` already has a Nautilus bridge:

- snapshot artifacts can be loaded as custom data
- a simple strategy can react to liquidation-map events
- a demo runner can attach the strategy to market data

That is useful, but it is not yet enough for execution-grade backtesting because
several important assumptions are still implicit:

- fill and slippage assumptions are minimal
- fee and funding treatment is not formalized as a backtest contract
- artifact provenance and market-data provenance are not bundled as a replay unit
- the current strategy logic is intentionally simple and heuristic

## Goal

Create a reproducible, execution-grade Nautilus backtest contract for event-driven
liquidation-map strategies, so that downstream reviewers can trust replay
results, compare strategy variants, and audit the exact inputs used.

## Scope

### In Scope

- formalize a replay unit combining artifact manifest, strategy config, and market data anchors
- define execution assumptions for fills, fees, slippage, and funding
- harden Nautilus loaders and runner interfaces for deterministic replay
- support replay of modeled-snapshot events alongside market data with explicit provenance
- produce machine-readable backtest result artifacts suitable for external review

### Out of Scope

- live order routing
- venue authentication and broker adapters
- production paper/live deployment
- strategy alpha research beyond what is needed to validate the harness contract

## Requirements

### Functional Requirements

- **FR-001**: The system MUST define a backtest replay contract that identifies:
  - liquidation artifact inputs
  - market data inputs
  - strategy configuration
  - execution assumptions
- **FR-002**: Nautilus backtest runs MUST be reproducible from retained manifests
  and pinned catalog references.
- **FR-003**: Backtest outputs MUST record fees, slippage assumptions, order
  status counts, and PnL in a machine-readable artifact.
- **FR-004**: The runner MUST fail explicitly when required artifact or market
  inputs are unavailable, instead of silently degrading into partial replay.
- **FR-005**: Strategy variants MUST be comparable under identical replay inputs.
- **FR-006**: The harness MUST support both Hyperliquid expert snapshots and
  Binance/Bybit modeled snapshots through a shared replay abstraction.

### Non-Functional Requirements

- **NFR-001**: Backtest replay SHOULD remain deterministic for identical input manifests.
- **NFR-002**: The harness SHOULD separate pure decision logic from venue/runtime glue.
- **NFR-003**: The contract SHOULD be reviewable without running Nautilus-specific
  code inside the consumer system.

## Success Criteria

- **SC-001**: A reviewer can reproduce a named backtest run from a retained
  manifest bundle and obtain materially identical results.
- **SC-002**: The backtest result artifact exposes enough detail to explain
  rejects, fills, closed positions, and PnL changes.
- **SC-003**: Replay no longer depends on ad hoc local knowledge of file paths or
  hidden runtime defaults.
