# Plan: Nautilus Event-Driven Backtest Hardening (spec-035)

## Phase 1: Replay Contract Freeze

1. Define the replay bundle shape
2. Freeze required provenance fields for artifacts and market data
3. Freeze result artifact fields for external review

## Phase 2: Loader and Runner Hardening

1. Harden artifact loaders with explicit failure semantics
2. Harden market-data bundle resolution and provenance capture
3. Harden the runner interface around replay config

## Phase 3: Execution Assumptions

1. Define slippage, fees, and funding assumptions
2. Persist those assumptions into replay manifests and results
3. Ensure result comparability across strategy variants

## Phase 4: Result Artifacts

1. Emit machine-readable backtest result bundles
2. Emit human-readable summary for external review
3. Validate deterministic replay from retained bundles

## Phase 5: Handoff

1. Produce sample replay bundles for Hyperliquid and Bybit/Binance
2. Document residual limits of the execution harness
3. Feed the approved contract into the paper/live runtime workstream
