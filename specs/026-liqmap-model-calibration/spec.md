# Spec 026: Liquidation Map Model Calibration & Multi-Provider Alignment

## Background — Findings from 3-Provider Analysis (2026-03-20)

### The Problem

Visual comparison of our liquidation maps vs CoinAnK and CoinGlass reveals
significant differences in absolute volumes, long/short ratios, and distribution
shape. The previous calibration metrics (spec-018/019 "bucket overlap 65-97%")
were misleading — they measured price-level overlap, not volume magnitude or
shape similarity.

### Data Collected

**Sources** (all captured 2026-03-19):
- Rektslug: live API (`/liquidations/coinank-public-map`)
- CoinAnK: captured via `capture_provider_api.py` (REST API, plaintext JSON)
- CoinGlass: captured via same script (AES-encrypted, decoded with `coinglass_decode_standalone.js`)

### Volume Scale Discrepancy

| Provider | ETH 1d Long | ETH 1d Short | Total | L/S Ratio |
|----------|-------------|--------------|-------|-----------|
| CoinGlass | 323M | 420M | 743M | 0.77 |
| **Rektslug** | **1,176M** | **2,773M** | **3,949M** | **0.42** |
| CoinAnK | 6,944M | 10,792M | 17,736M | 0.64 |

| Provider | BTC 1w Long | BTC 1w Short | Total | L/S Ratio |
|----------|-------------|--------------|-------|-----------|
| CoinGlass | ~1,176M | ~1,148M | ~2,324M | 1.02 |
| **Rektslug** | **437M** | **3,893M** | **4,330M** | **0.11** |
| CoinAnK | 17,931M | 16,192M | 34,123M | 1.11 |

**Key observations**:
1. Rektslug is 5x CoinGlass but 5x below CoinAnK
2. L/S ratio is severely unbalanced for BTC 1w (0.11 vs ~1.0 for both others)
3. No two providers agree on absolute numbers — this is structural, not a bug

### Shape Comparison (Normalized Distribution Analysis)

Using KS test, Pearson correlation, Wasserstein distance, and overlap coefficient
on normalized [0,1] distributions:

**CoinAnK vs CoinGlass** (ETH 1d):
- Pearson r: +0.21 (WEAK correlation)
- KS statistic: 0.21 (DIFFERENT cumulative shapes)
- Wasserstein distance: 0.10 (CLOSE earth-mover distance)
- Overlap coefficient: 0.65 (MEDIUM)
- Peak locations: CoinAnK peaks at -0.40 (below price), CoinGlass at -0.25

**CoinAnK vs CoinGlass** (ETH 1w):
- Pearson r: +0.01 (NO correlation)
- KS statistic: 0.11 (SIMILAR cumulative shapes)
- Wasserstein distance: 0.06 (CLOSE)
- Overlap coefficient: 0.70 (HIGH)
- Peak locations: CoinAnK peaks below price (-0.33), CoinGlass peaks above (+0.25)

**Verdict**: Even CoinAnK and CoinGlass don't agree on distribution shape.
The two "reference" providers have weak correlation (r=0.01 to 0.21).
This means there is NO ground truth to calibrate against.

### Root Cause Analysis

**Why volumes differ across providers**:

| Factor | CoinGlass | Rektslug | CoinAnK |
|--------|-----------|----------|---------|
| Volume meaning | Collateral (OI/leverage) | OI-scaled | Notional (OI * leverage) |
| Leverage tiers | 10x, 25x, 50x, 100x | 25x-100x (9 tiers) | 25x-100x (9 tiers) |
| Side inference | Unknown | Candle direction + OI delta | Unknown |
| Low leverage (5x, 10x) | Included | Missing from public builder | Excluded from public |
| OI decrease handling | Unknown | Filtered out (only growing OI) | Unknown |

**Why our L/S ratio is wrong**:
1. Side inference in `calculate_liquidations_oi_based()` filters candles where
   `OI delta <= 0` (line ~1330: `ELSE NULL -- Ignore neutral candles or OI decrease`)
2. In a trending market, bullish candles have more OI increase than bearish ones,
   so we systematically see more "buy" (long) signals that get filtered when price
   reverses → shorts are over-represented
3. CoinAnK/CoinGlass likely don't filter by OI direction — they distribute OI
   across both sides more evenly

### What Makes a Good Liq Map?

For **trading utility**, what matters most:
1. **WHERE** are the liquidation clusters (relative to current price) — SHAPE
2. **HOW MUCH** liquidation pressure exists (order of magnitude) — SCALE
3. **WHICH SIDE** dominates (long vs short balance) — RATIO

Absolute dollar values are less important than relative distribution.

## Proposed Changes (Spec Scope)

### In Scope

#### P1: Fix L/S Ratio (Critical)
- Remove the `OI delta > 0` filter for side inference
- Instead: distribute OI evenly across long/short, weighted by candle direction
  proportionally (not binary filter)
- Target: L/S ratio between 0.6-1.2 for 1w timeframes (matching CoinAnK/CoinGlass)

#### P2: Add Multi-Model Support
- Add a `model` query parameter to the public builder: `coinank` (default), `coinglass`
- `coinank` model: notional-based (current approach, volume = OI * leverage weight)
- `coinglass` model: collateral-based (volume = OI / leverage for each tier)
- Frontend selector to switch between models

#### P3: Volume Scale Alignment
- Add leverage multiplier to align with CoinAnK scale (~5-6x current)
- Alternative: show both scales in frontend (left axis CoinAnK-like, right axis CoinGlass-like)

#### P4: Refresh CoinGlass Decoder Pipeline
- Automate `_app-*.js` bundle download (currently manual)
- Integrate `coinglass_decode_standalone.js` into comparison pipeline
- Add scheduled comparison (weekly) with automated shape metrics

### Out of Scope
- Real-time CoinGlass data (encrypted, requires periodic bundle refresh)
- Matching CoinAnK exactly (no ground truth, different methodology)
- New frontend views (defer to spec-025 WebSocket)

## Dependencies
- spec-024 heatmap cache (completed)
- `scripts/coinglass_decode_standalone.js` (created in this analysis)
- `scripts/shape_comparison_analysis.py` (created in this analysis)

## Success Criteria
- SC-001: L/S ratio for BTC 1w between 0.6-1.4 (currently 0.11)
- SC-002: L/S ratio for ETH 1d between 0.4-1.0 (currently 0.42 — borderline)
- SC-003: Shape metrics vs CoinAnK improve (Pearson r > 0.4 after calibration)
- SC-004: Multi-model endpoint works with `?model=coinank` and `?model=coinglass`
- SC-005: Automated weekly comparison pipeline produces reports
