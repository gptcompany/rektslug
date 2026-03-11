# Feature Specification: Visual Comparison Harness

**Feature ID**: 020
**Canonical Source**: `specs/020-visual-comparison-harness/spec.md`

This mirror exists for `.specify` compatibility.

The source of truth remains:
- `specs/020-visual-comparison-harness/spec.md`

The implementation goal is unchanged:
- build reusable screenshot/score/manifest infrastructure
- support current `liq-map` work first, with `local + CoinAnK + plotly` as the first green path
- remain extensible to future heatmap comparisons
- keep product adapters separate from renderer adapters

Internal delivery is now split into three milestones:
- `Milestone 1 / MVP`: `local + CoinAnK + liq-map + plotly`
- `Milestone 2 / Hardening`: failure modes, deterministic artifacts, runtime/size gates
- `Milestone 3 / Extension`: seams for `liq-heat-map`, `lightweight`, and future provider wiring
