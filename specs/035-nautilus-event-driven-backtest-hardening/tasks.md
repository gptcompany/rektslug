# Tasks: spec-035 Nautilus Event-Driven Backtest Hardening

## Phase 1: Replay Contract

- [x] T001 Freeze the replay bundle schema for artifact, market data, strategy config,
  and execution assumptions
- [x] T002 Freeze the machine-readable result artifact schema

## Phase 2: Loader Hardening

- [x] T003R RED: Add failing tests for missing/ambiguous replay inputs
- [x] T004 Harden liquidation-event loader failure semantics
- [x] T005 Harden raw catalog and market-data provenance capture
- [x] T006 Remove silent or unclear replay defaults where they hide missing inputs

## Phase 3: Runner Hardening

- [x] T007R RED: Add failing tests for replay config persistence and reproducibility
- [x] T008 Persist replay config and execution assumptions into result artifacts
- [x] T009 Record fees, slippage assumptions, funding assumptions, and order lifecycle counts

## Phase 4: Result Artifacts

- [x] T010R RED: Add failing tests for machine-readable backtest result bundles
- [x] T011 Implement result bundle writing and sample reproduction helpers
- [x] T012 Validate deterministic replay on retained sample bundles

## Phase 5: Review Handoff

- [x] T013 Produce one Hyperliquid replay bundle for external review
- [x] T014 Produce one modeled-snapshot replay bundle for external review
- [x] T015 Document known limitations and assumptions that still separate this
  harness from paper/live trading
