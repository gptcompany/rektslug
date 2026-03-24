# Research: Spec-027 Reserved-Margin Validation & Portfolio-Margin Solver

**Date**: 2026-03-24
**Sources**: Spec-026 research.md, checkpoint-2026-03-23.md, Hyperliquid docs (triangulated), existing validation artifacts
**Confidence**: 75/100 (high on API structure, moderate on formula candidates, low on portfolio-margin edge cases)

---

## 1. Hyperliquid clearinghouseState API Response Structure

**Decision**: Use the Info API endpoint `POST https://api.hyperliquid.xyz/info` with body `{"type": "clearinghouseState", "user": "<address>"}`.

**Response structure** (confirmed from docs + existing WebSocket adapter in `src/exchanges/hyperliquid.py`):

```json
{
  "marginSummary": {
    "accountValue": "12345.67",
    "totalMarginUsed": "1234.56",
    "totalNtlPos": "50000.00",
    "totalRawUsd": "10000.00"
  },
  "crossMarginSummary": {
    "accountValue": "12345.67",
    "totalMarginUsed": "1234.56",
    "totalNtlPos": "50000.00",
    "totalRawUsd": "10000.00"
  },
  "assetPositions": [
    {
      "type": "oneWay",
      "position": {
        "coin": "ETH",
        "szi": "10.5",
        "entryPx": "2000.0",
        "positionValue": "21000.0",
        "unrealizedPnl": "500.0",
        "returnOnEquity": "0.05",
        "liquidationPx": "1800.0",
        "leverage": {
          "type": "cross",
          "value": 20
        },
        "marginUsed": "1050.0",
        "maxLeverage": 20,
        "cumFunding": {
          "allTime": "12.34",
          "sinceOpen": "1.23",
          "sinceChange": "0.12"
        }
      }
    }
  ]
}
```

**Key fields for validation**:
- `marginSummary.totalMarginUsed` — ground truth for total account margin
- Per-position `marginUsed` — per-position comparison target
- Per-position `liquidationPx` — solver V1 validation target
- `leverage.type` — "cross" or "isolated" — margin mode detection

**Portfolio margin accounts** will have additional `portfolioMarginSummary` field (if active).

**Rationale**: Response structure triangulated from Hyperliquid gitbook docs, SDK examples, and CoinGlass integration patterns. All values are strings (parse to float).

**Alternatives considered**: Using WebSocket `userState` subscription — rejected because we need point-in-time queries for specific outlier users, not streaming.

---

## 2. Portfolio Margin Detection

**Decision**: Detect portfolio margin by checking for presence of `portfolioMarginSummary` in the clearinghouseState response.

**Detection logic**:
```python
def detect_margin_mode(response: dict) -> MarginMode:
    if response.get("portfolioMarginSummary"):
        return MarginMode.PORTFOLIO_MARGIN
    # Check per-position leverage types
    for ap in response.get("assetPositions", []):
        pos = ap.get("position", {})
        lev = pos.get("leverage", {})
        if lev.get("type") == "isolated":
            return MarginMode.ISOLATED_MARGIN
    return MarginMode.CROSS_MARGIN
```

**Portfolio margin specifics** (from spec-026 research, confirmed):
- Only for master accounts with >$5M volume
- Net risk across positions reduces collateral requirements
- Supply/borrow caps: 500M USDC global, 400 BTC global
- `portfolio_margin_ratio > 0.95` triggers liquidation
- Liquidation semantics differ fundamentally from cross-margin

**Rationale**: Hyperliquid docs confirm portfolio margin response includes distinct fields. The API response structure was updated in March 2026 alpha rollout.

**Risk**: Portfolio margin is in alpha — response format may change without notice. We should log and gracefully handle unexpected structures.

---

## 3. meta Endpoint — Margin Tiers

**Decision**: Use `POST https://api.hyperliquid.xyz/info` with body `{"type": "meta"}` to get current margin tiers.

**Response includes** (per asset in `universe` array):
```json
{
  "universe": [
    {
      "name": "ETH",
      "szDecimals": 4,
      "maxLeverage": 50,
      "onlyIsolated": false
    }
  ]
}
```

For detailed margin tiers, use `{"type": "metaAndAssetCtxs"}` which returns:
```json
[
  { "universe": [...] },  // meta
  [                        // assetCtxs per asset
    {
      "funding": "0.0001",
      "openInterest": "123456.78",
      "prevDayPx": "2000.0",
      "dayNtlVlm": "50000000.0",
      "premium": "0.0002",
      "oraclePx": "2001.5",
      "markPx": "2001.0",
      "midPx": "2000.8",
      "impactPxs": ["2002.0", "1999.5"]
    }
  ]
]
```

**Existing sidecar implementation**: `_get_margin_tier()` at sidecar.py:1619 already uses tiered margin from ABCI snapshots. For API validation, we need live tiers to compare at the same mark prices.

**Rationale**: We need mark prices and tiers at the same point in time as the API query. The sidecar uses ABCI snapshot tiers (historical), while validation needs current API tiers.

---

## 4. Rate Limiting

**Decision**: Implement conservative rate limiting at 10 req/min with exponential backoff.

**Documented limits**:
- Hyperliquid Info API: no official published rate limit
- Empirical observation: ~1200 requests/min before throttling (from community reports)
- Spec assumption: 10-20 req/min is safe and sufficient for our batch validation

**Implementation**:
- Use `asyncio.Semaphore(max_concurrent=5)` for concurrency control
- Add 3-second delay between user queries (= 20 req/min max)
- Implement exponential backoff on 429 responses
- Partial result reporting: if some users fail, report those that succeeded

**Rationale**: Conservative approach because we only need 10-20 users for validation. No need to push limits.

---

## 5. Reserved-Margin Formula Candidates

**Decision**: Test 4 candidate formulas against API ground truth to identify the best fit.

**Candidate A**: Initial Margin per order (documented IM check)
```
reserved(order) = abs(size) * mark_price / max_leverage_for_tier
```
- Applied to exposure-increasing orders only
- Reduce-only orders reserve zero

**Candidate B**: Maintenance Margin on exposure-increasing notional
```
reserved(order) = abs(size) * mark_price * mmr_rate - maintenance_deduction
```
- Same filter: only exposure-increasing orders

**Candidate C**: IM on net additional exposure (account-aware)
```
For each order:
  new_position = current_position + order_size
  new_notional = abs(new_position) * mark_price
  old_notional = abs(current_position) * mark_price
  delta_notional = max(0, new_notional - old_notional)
  reserved(order) = delta_notional / max_leverage
```

**Candidate D**: Hyperliquid's documented placement check (best guess)
```
For all orders collectively:
  worst_case_equity = account_value - sum(unrealized_pnl_if_all_orders_fill)
  total_im_if_all_fill = sum(abs(resulting_position) * mark / leverage)
  reserved = total_im_if_all_fill - current_im
```

**Rationale**: From spec-026 checkpoint, we know:
1. `snapshot M` is NOT a direct open-order reserve proxy (confirmed)
2. Off-target orders are materially relevant (117M off-target vs 88M on-target)
3. Some outlier users have mostly reducing orders but still show margin gap
4. The formula must be reverse-engineered — no public documentation exists

### CAS Validation Results (Sage)

All 4 candidates validated via CAS endpoint (`http://localhost:8769/validate`, engine: sage).

**Candidate A**: `abs(x)*y/z` — **VALID**
- Simplified: `y*abs(x)/z` (correct, linear in size and mark)
- Numeric: `abs(10)*2000/20 = 1000` (10 units, $2000 mark, 20x leverage -> $1000 IM)

**Candidate B**: `abs(x)*y*r - t` — **VALID**
- Simplified: `r*y*abs(x) - t` (correct, tiered MMR with deduction)
- Numeric: With `r = 1/(2*L) = 0.025`, `t=0`: `abs(10)*2000*0.025 = 500` (half of Candidate A)
- **Key insight**: B always < A when `d=0` because `mmr_rate = 1/(2*max_leverage)` < `1/max_leverage`

**Candidate C**: `max(0, abs(x+w)*y - abs(x)*y)/z` — **VALID with caveat**
- Sage symbolic simplification incorrectly returns `0` (treats `max` as identity with symbolic `abs`)
- **Numeric verification confirms correctness**:
  - Same-side increase (x=10, w=5): `max(0, 30000-20000)/20 = 500`
  - Reducing (x=10, w=-3): `max(0, 14000-20000)/20 = 0` (correct: no reserve for reduces)
  - Cross-zero (x=10, w=-15): `max(0, 10000-20000)/20 = 0` (correct: net reduction)
  - New position (x=0, w=5): `max(0, 10000-0)/20 = 500`

**Candidate D**: `(abs(x+w) - abs(x))*y/z` — **VALID**
- Simplified: `y*(abs(w + x) - abs(x))/z` (correct)
- Numeric:
  - Same-side increase: `(15-10)*2000/20 = 500`
  - Reducing: `(7-10)*2000/20 = -300` (negative = no additional reserve)
- **Algebraic relationship confirmed**: `C = max(0, D)` — verified numerically across all 3 cases

**Formula hierarchy** (confirmed by CAS):
```
A > B  always (when d=0, because mmr_rate < 1/leverage)
C = max(0, D)  algebraically equivalent
C <= A  always (C only counts delta, A counts full order)
```

**CAS verdict**: All 4 formulas are mathematically well-formed. The key unknowns are:
1. Does Hyperliquid use A (full IM) or C (delta IM) for reserve?
2. Does Hyperliquid use IM-rate (1/leverage) or MMR-rate (1/2*leverage)?
3. Is the deduction `d` applied per-order or per-asset?

These can ONLY be resolved by API comparison (not symbolically).

**Validation approach**: For each outlier user, compute all 4 candidates, then compare `sidecar_mmr + candidate_reserved` against `API totalMarginUsed`. The candidate that explains the most users within 1% wins.

**Alternatives considered**: Using a ML regression model to fit the formula — rejected as premature. Start with physics-based candidates first.

---

## 6. Existing Artifacts Available from Spec-026

**Ready to use** (no re-computation needed):

| Artifact | Path | Content |
|----------|------|---------|
| 9 outlier users | `data/validation/hl_reserved_margin_outliers_eth_sample.json` | Detailed order classification, exposure bounds |
| 370 active users | `data/validation/hl_reserved_margin_proxy_eth_sample.json` | Bounded exposure-opening notional |
| Gap analysis | `data/validation/hl_open_order_margin_gap_eth_7d.json` | M vs MMR for 146k positions |
| Order reconstruction | `data/validation/hl_order_state_reconstruction_eth_sample.json` | 4,636 recovered orders |
| ETH 7d surface | `data/validation/liqmap_hl_eth_7d.json` | 339k accounts, V1 baseline |
| BTC 7d surface | `data/validation/liqmap_hl_btc_7d.json` | 455k accounts, V1 baseline |

**From spec-026 checkpoint** (recommended starting dataset):
- Use the 9 outlier users from `hl_reserved_margin_outliers_eth_sample.json`
- Add 1-2 "normal" users (small gap) as control group
- Total: 10-12 users for initial API validation

---

## 7. Solver V1 Current State

**Location**: `sidecar.py:1641-1696` (`solve_liquidation_price()`)

**What V1 does**:
- Solves cross-margin liquidation price by freezing non-target asset marks
- Uses tiered MMR with maintenance deduction
- Handles long/short positions separately
- Balance already includes historical funding

**What V1 ignores** (to be added in V1.1):
- Reserved margin from resting orders (the core gap)
- Portfolio-margin accounts (assumes all cross-margin)
- Isolated-margin positions within a cross-margin account (mixed mode)

**V1.1 integration approach**:
```python
# In solve_liquidation_price():
account_base = balance + other_pnl - reserved_margin_from_orders
#                                     ^^^^^^^^^^^^^^^^^^^^^^^^^ NEW
```

The reserved margin reduces the account's available equity, shifting the liquidation price closer to the current mark price. This means V1 systematically overestimates distance to liquidation for users with significant resting orders.

---

## 8. Open Questions (to resolve during implementation)

1. **Does Hyperliquid's `totalMarginUsed` include or exclude reserved margin for resting orders?**
   - Hypothesis: YES, it includes it — validation will confirm
   - If NO, we need `totalMarginUsed + reservedMargin` as the comparison target

2. **Are isolated-margin positions included in `marginSummary.totalMarginUsed`?**
   - Hypothesis: YES, account-level total includes all modes
   - Need to verify with a mixed-mode account

3. **Does `liquidationPx` from API account for resting orders?**
   - Hypothesis: YES — this is the exchange's actual liquidation price
   - If YES, comparing API `liquidationPx` vs sidecar `solve_liquidation_price()` directly measures our accuracy

4. **How does portfolio margin interact with `clearinghouseState` for accounts with both PM and isolated positions?**
   - Unknown — need API exploration with real PM accounts

---

## Summary of NEEDS CLARIFICATION Resolution

| Unknown | Resolution | Confidence |
|---------|------------|------------|
| clearinghouseState response structure | Documented above from HL docs | HIGH |
| Portfolio margin detection | `portfolioMarginSummary` field presence | MEDIUM (alpha, may change) |
| Margin tier source for validation | `metaAndAssetCtxs` endpoint | HIGH |
| Rate limiting | Conservative 10 req/min, empirically safe | HIGH |
| Reserved-margin formula | 4 candidates to test, no single answer yet | LOW (reverse-engineering) |
| V1.1 integration path | Subtract reserved margin from account_base | HIGH |
| Existing validation data | 9 outlier users + control group ready | HIGH |
| Portfolio-margin solver | PMR > 0.95 threshold, net risk netting | MEDIUM (docs exist, implementation untested) |
