# Evidence Package: spec-037 Nautilus Liquidation Bridge Operational Closeout

**Status**: Draft template
**Created**: 2026-04-19

This package must be completed during implementation. Do not mark spec-037
implemented until every required section below contains concrete evidence.

## Commit Ledger

| Repo | Commit | Purpose | Verification |
|------|--------|---------|--------------|
| `rektslug` | TBD | TBD | TBD |
| `nautilus_dev` | TBD | TBD | TBD |

## Gate Results

| Gate | Status | Evidence |
|------|--------|----------|
| `G0` dry-run | TBD | TBD |
| `G1` smoke | Passed baseline | Existing smoke/runbook evidence |
| `G2` soak | Partial baseline | Existing 2-cycle soak; review-grade soak TBD |
| `G3` continuous paper/testnet | TBD | TBD |
| `G4` external review | TBD | TBD |

## Required Evidence

### Long Soak

- command:
- aggregate JSON path:
- cycles requested:
- cycles passed:
- cycles failed:
- final open positions:
- final open orders:
- residual orders cleaned:
- total PnL:
- notes:

### Real-Signal Dry-Run

- command:
- runtime window:
- signals seen:
- signals rejected:
- signals accepted:
- venue orders submitted:
- report path:
- notes:

### Real-Signal Testnet/Paper

- command:
- runtime window:
- signals seen:
- signals accepted:
- positions opened:
- positions closed:
- feedback rows persisted:
- final open positions:
- final open orders:
- report path:
- notes:

### Recovery And Fault Injection

| Fault Point | Result | Evidence | Notes |
|-------------|--------|----------|-------|
| pre-submit | TBD | TBD | TBD |
| post-submit/pre-fill | TBD | TBD | TBD |
| open-position/pre-close | TBD | TBD | TBD |
| post-close/pre-feedback | TBD | TBD | TBD |
| Redis unavailable | TBD | TBD | TBD |
| DuckDB unavailable | TBD | TBD | TBD |

## Residual Risks

- TBD

## Promotion Decision

`G5` limited live remains out of scope. A future limited-live decision requires
a separate explicit approval/spec after this evidence package is complete.
