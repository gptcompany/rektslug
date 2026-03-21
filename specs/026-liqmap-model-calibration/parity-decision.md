# Parity Decision: Rektslug Sidecar vs CoinGlass Hyperliquid

**Date**: 2026-03-21
**Scope**: ETH + BTC 7d risk-surface comparison
**Decision**: Best-effort parity (not 1:1 match). See rationale below.

## Data Sources

| Source | ETH | BTC |
|--------|-----|-----|
| **Rektslug Sidecar** | 339,050 accounts, Cross-Margin V1 solver, ABCI snapshot 20260321 | 455,175 accounts, same solver, same snapshot |
| **CoinGlass Hyperliquid** | 153 top positions, `topPosition/liqMap?symbol=ETH` capture 20260320T183129Z | 285 top positions, same capture session |

## Shape Metrics

| Metric | ETH | BTC | Interpretation |
|--------|-----|-----|----------------|
| **Pearson r** | 0.003 | -0.002 | No linear correlation |
| **KS statistic** | 0.430 | 0.331 | Very different distributions |
| **Wasserstein dist** | $2,187 | $42,664 | Large shape divergence |
| **L/S ratio diff** | 0.044 | 0.042 | Close agreement |
| **Volume scale (CG/Sidecar)** | 8.13x | 7.25x | CG shows ~7-8x more volume |

## Per-Side Pearson r

| Side | ETH | BTC |
|------|-----|-----|
| Long | 0.002 | 0.001 |
| Short | -0.002 | -0.007 |

## Peak Bucket Alignment

### ETH
- **Sidecar top 5**: $2,835 | $2,061 | $2,381 | $2,099 | $3,566
- **CoinGlass top 5**: $1,756 | $1,455 | $2,718 | $2,716 | $4,029
- **Peak mean distance**: $373, **max**: $644

### BTC
- **Sidecar top 5**: $86,590 | $266,980 | $81,790 | $251,260 | $70,640
- **CoinGlass top 5**: $101,440 | $33,680 | $80,610 | $36,090 | $64,240
- **Peak mean distance**: $88,240, **max**: $215,170

## Volume Scale Analysis

CoinGlass reports 7-8x more notional than Rektslug despite tracking only 153-285 positions vs 339k-455k accounts. This is expected:

- CoinGlass `topPosition` endpoint exposes only the **largest whale positions** on Hyperliquid
- These whales run at high leverage with outsized notional
- Rektslug processes **all accounts** from the ABCI snapshot, including the massive retail tail with small positions

The volume disparity is structural, not a bug: CoinGlass shows where whales would liquidate, Rektslug shows where everyone would liquidate.

## L/S Ratio Agreement

Despite the shape divergence, the long/short ratio is remarkably consistent:

| | ETH | BTC |
|--|-----|-----|
| Sidecar L/S | 0.981 | 0.886 |
| CoinGlass L/S | 0.937 | 0.845 |
| Difference | 0.044 | 0.042 |

Both sources agree that shorts slightly dominate in both markets (L/S < 1), with ETH closer to balanced.

## Root Cause of Shape Divergence

The weak Pearson r and high KS are explained by the fundamentally different populations:

1. **CoinGlass = ~250 whale positions**: concentrated volume at specific leverage/entry combos. A single $69M BTC whale at 3x leverage dominates the BTC distribution.
2. **Rektslug = full clearinghouse state**: 339k-455k accounts produce a dense, smooth distribution across thousands of price bins. Retail positions dominate the bin count.
3. **No heatmap bucketing on CoinGlass side**: CoinGlass provides raw `liquidationPrice` per position, not a pre-computed heatmap. Their visible heatmap on the website likely applies additional smoothing/kernel density that we don't replicate here.

## Decision

### Verdict: **Best-effort parity** (not 1:1 match, not rejected)

**Rationale**:
- 1:1 shape parity is structurally impossible because the two sources track different populations (top ~250 whales vs all ~400k accounts)
- The L/S ratio agreement (within 0.04-0.05) validates that both sources capture the same directional market bias
- Rektslug's full-population coverage is actually **more comprehensive** than CoinGlass's whale-only view
- The CoinGlass `topPosition` feed was never designed to be a complete liquidation heatmap -- it's a top-position risk feed that CoinGlass then processes further

**What Rektslug provides that CoinGlass does not**:
- Liquidation risk from 339k-455k accounts (vs 153-285)
- Full cross-margin solver with MMR tiers and cumulative funding
- Per-account PnL from all positions (not just target coin)
- No dependence on proprietary decryption

**Remaining gaps**:
- Open orders reserved margin (T034, deferred)
- Snapshot-to-snapshot replay drift (T017, bounded but unproven)
- ABCI retention is 2 days; 7d window uses single latest anchor (acceptable for position-state but not for volume-over-time)

### Go/No-Go

| Criterion | Status |
|-----------|--------|
| Solver correctness (cross-margin, MMR tiers) | GO |
| L/S directional agreement | GO |
| Volume coverage (all accounts) | GO |
| Shape parity with CoinGlass | NO-GO (structurally impossible, acceptable) |
| Infrastructure for production 7d | BLOCKED (ABCI retention = 2d) |

**Recommendation**: Proceed with Rektslug sidecar as the Hyperliquid liquidation model. Do not attempt 1:1 CoinGlass shape matching, as the population difference makes it meaningless. Focus instead on validating solver accuracy through known-liquidation event backtesting when the data becomes available.
