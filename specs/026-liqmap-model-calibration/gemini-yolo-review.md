# Gemini YOLO Review Brief: Spec 026 Phase 4 Sidecar Design

## Scope

Review only these files:

- `specs/026-liqmap-model-calibration/spec.md`
- `specs/026-liqmap-model-calibration/plan.md`
- `specs/026-liqmap-model-calibration/tasks.md`
- `specs/026-liqmap-model-calibration/sidecar-design.md`

## Context

This round documents the architecture and proof strategy for exact BTC/ETH
Hyperliquid parity under multi-asset cross-margin.

Key decisions already made:

- parity engine must stay outside `hyperliquid-node`
- `hyperliquid-node` remains canonical collector / state-anchor layer
- relevant BTC/ETH accounts must retain off-target assets if those assets affect cross-margin semantics
- local ABCI anchors are confirmed for roughly `2d`; exact `7d` replay is NOT yet proven
- first builder V0 uses profile-resolved bin size and target-notional bucket accumulation

## Review Mode

Use YOLO mode: be aggressive, skeptical, and line-specific.

Do not spend time on style nits. Focus on:

- contradictions between files
- claims that overstate exactness or reconstructability
- hidden assumptions that would break multi-asset cross-margin parity
- missing proof obligations for replay exactness
- places where the first builder V0 accidentally claims vendor parity instead of a bounded internal model
- node/sidecar boundary leaks
- task-state inaccuracies (`[X]` marked too early, missing open work, wrong dependency ordering)

## Questions To Attack

1. Does any file accidentally claim exact `7d` parity, when current evidence only supports snapshot-anchored exactness on the retained `2d` ABCI window?
2. Does the retained-account rule really preserve all state required for multi-asset cross-margin accounts, including open-order / reserved-margin effects?
3. Is `First Builder V0 Parameters` framed correctly as a builder choice rather than a claim about CoinGlass methodology?
4. Are there any missing invariants required to call replay `exact` at later anchors?
5. Is the sidecar boundary truly clean, or do any tasks/deliverables still imply pushing parity logic into `hyperliquid-node`?
6. Are any Phase 4 tasks marked complete before the repo actually proves the underlying requirement?

## Expected Output

Return only high-signal findings, ordered by severity.

For each finding include:

- severity (`P0`, `P1`, `P2`)
- file and line reference
- why the claim/design is wrong or under-specified
- what needs to change to make it rigorous

If there are no findings, say that explicitly and list residual risks.
