# Tasks: spec-035 Nautilus Event-Driven Backtest Hardening

## Phase 1: Replay Contract

- [ ] T001 Freeze the replay bundle schema for artifact, market data, strategy config,
  and execution assumptions
- [ ] T002 Freeze the machine-readable result artifact schema

## Phase 2: Loader Hardening

- [ ] T003R RED: Add failing tests for missing/ambiguous replay inputs
- [ ] T004 Harden liquidation-event loader failure semantics
- [ ] T005 Harden raw catalog and market-data provenance capture
- [ ] T006 Remove silent or unclear replay defaults where they hide missing inputs

## Phase 3: Runner Hardening

- [ ] T007R RED: Add failing tests for replay config persistence and reproducibility
- [ ] T008 Persist replay config and execution assumptions into result artifacts
- [ ] T009 Record fees, slippage assumptions, funding assumptions, and order lifecycle counts

## Phase 4: Result Artifacts

- [ ] T010R RED: Add failing tests for machine-readable backtest result bundles
- [ ] T011 Implement result bundle writing and sample reproduction helpers
- [ ] T012 Validate deterministic replay on retained sample bundles

## Phase 5: Review Handoff

- [ ] T013 Produce one Hyperliquid replay bundle for external review
- [ ] T014 Produce one modeled-snapshot replay bundle for external review
- [ ] T015 Document known limitations and assumptions that still separate this
  harness from paper/live trading
