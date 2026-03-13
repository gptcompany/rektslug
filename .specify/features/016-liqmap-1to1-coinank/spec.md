# Feature Specification: Liq-Map 1:1 Coinank Visual Match

**Feature ID**: 016
**Canonical Source**: `specs/016-liqmap-1to1-coinank/spec.md`

This mirror exists for `.specify` compatibility.

The source of truth remains:
- `specs/016-liqmap-1to1-coinank/spec.md`

Status note:
- `spec-016` now serves mainly as the historical frontend visual checklist
- the remaining public-route backend/data-path gap is tracked in `spec-022`

The implementation goal is unchanged at a high level:
- achieve near 1:1 visual match with CoinAnk for `liq-map`
- keep scope on BTC/ETH using the same page
- keep `liq-heat-map` out of scope
- keep runtime/freshness gates aligned to latest upstream-available data
