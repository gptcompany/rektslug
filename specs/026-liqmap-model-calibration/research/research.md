# Research: Spec-026 Next Steps — Reserved Margin, Carry-In, Consumer Checkpoint

**Date**: 2026-03-24
**Query**: Reserved-margin formula derivation, carry-in state bounding, consumer checkpoint design for Hyperliquid sidecar
**Sources**: PePeRS pipeline (2 runs), WebSearch (8 queries), Hyperliquid official docs, Cosmos/Tendermint ADRs, exploit post-mortems
**Confidence**: 72/100 (high on architecture, moderate on formula derivation, low on academic precedent)

---

## Key Findings

### 1. Hyperliquid Margin System — Official Semantics (Triangulated: 4 sources)

**Source**: [Hyperliquid Docs: Margining](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margining), [Margin Tiers](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margin-tiers), [Liquidations](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations)

Core formulas confirmed:
- **Initial Margin (IM)**: `position_size * mark_price / leverage`
- **Maintenance Margin (MM)**: `notional * MM_rate - maintenance_deduction` (tiered)
- **MM Rate**: `1 / (2 * max_leverage_at_tier)` — e.g., 20x -> 2.5%
- **Liquidation price**: `liq_price = price - side * margin_available / position_size / (1 - l * side)` where `l = 1 / MAINTENANCE_LEVERAGE`
- **Transfer margin**: `max(initial_margin_required, 0.1 * total_position_value)`

**Critical for reserved margin**: Margin checks happen at TWO points:
1. When an order is **placed** (uses IM at current mark)
2. When a **resting order is matched** (re-checks IM at current mark)

This means Hyperliquid does NOT pre-reserve a fixed margin amount for resting orders — instead it checks at placement time and re-checks at fill time. The "reserved margin" is the IM computed at placement, but it can become stale if mark moves.

**No public formula exists for "open order reserved margin"** — the clearinghouse source code is closed. The `order_book_server` repo is only a data-streaming layer.

### 2. Portfolio Margin Changes (March 2026) — Moving Target Risk (Triangulated: 3 sources)

**Source**: [CoinDesk: Portfolio Margin Alpha](https://www.coindesk.com/markets/2026/03/10/hyperliquid-s-new-upgrade-to-let-traders-take-bigger-bets-with-less-capital), [Hyperliquid Docs: Portfolio Margin](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/portfolio-margin)

Hyperliquid is actively rolling out portfolio margin (alpha phase March 2026):
- Net risk across positions reduces collateral requirements
- Only for master accounts with >$5M volume
- Strict supply/borrow caps (500M USDC global, 400 BTC global)
- `portfolio_margin_ratio > 0.95` triggers liquidation

**Impact on sidecar**: Portfolio margin accounts will have DIFFERENT liquidation semantics than standard cross-margin accounts. The solver must detect which margin mode each account uses.

### 3. Academic Gap — No Formal Reserved-Margin Theory (Triangulated: 3 sources)

**Source**: [ResearchGate: DeFi Liquidations Study](https://www.researchgate.net/publication/355838152_An_empirical_study_of_DeFi_liquidations_incentives_risks_and_instabilities), [arXiv: Autodeleveraging](https://arxiv.org/html/2512.01112v2), PePeRS pipeline (0 relevant papers)

There is **no formal academic study** of reserved-margin semantics for perpetual futures exchanges. The literature gap is confirmed by:
- PePeRS pipeline: 0 relevant papers from arXiv + OpenAlex on "cross-margin reserved margin clearinghouse"
- Web search: no results for "initial margin requirement resting order reserved margin perpetual futures formula"
- The closest academic work is on DeFi lending liquidations (Aave/Compound), not perp exchange margin systems

**Implication**: We cannot derive our formula from academic literature. We must reverse-engineer from Hyperliquid's observable behavior.

### 4. Order Book Checkpoint/Replay Architecture (Triangulated: 4 sources)

**Source**: [Tendermint ADR-042: State Sync](https://github.com/tendermint/tendermint/blob/master/docs/architecture/adr-042-state-sync.md), [ADR-053: State Sync Prototype](https://github.com/tendermint/tendermint/blob/master/docs/architecture/adr-053-state-sync-prototype.md), [Cosmos SDK Snapshots](https://pkg.go.dev/github.com/cosmos/cosmos-sdk/snapshots), [Jane Street: Building an Exchange](https://www.janestreet.com/tech-talks/building-an-exchange/)

Standard checkpoint/replay patterns well-documented:

**Cosmos/Tendermint ABCI (directly relevant — Hyperliquid uses ABCI)**:
- Snapshots must be **periodic, deterministic, consistent, asynchronous, chunked, garbage-collected**
- Recovery: load latest snapshot + replay WAL entries after it
- Cosmos SDK: `state-sync.snapshot-interval` config, binary files in `<node_home>/data/snapshots/`
- Pruning interaction: snapshot heights are preserved until snapshot is complete

**Exchange matching engine (Jane Street, Liquibook)**:
- WAL (Write-Ahead Log) for every event
- Periodic snapshots of in-memory order book
- Recovery = snapshot + WAL replay
- Sequence numbers for reconciliation and exactly-once guarantees
- Single-threaded sequencer per instrument for determinism

**Hyperliquid-specific**:
- `periodic_abci_states/` are the snapshots (~15min cadence, ~1.1GB each)
- 2-day retention locally
- Consumer must own retention beyond producer's rolling window
- No WAL equivalent exposed to consumers — only block-level event streams

### 5. Exploit History — Systemic Margin Failures (Triangulated: 5 sources)

**Source**: [Halborn: ETH Hack March 2025](https://www.halborn.com/blog/post/explained-the-hyperliquid-hack-march-2025), [OAK Research: JELLY Attack](https://oakresearch.io/en/analyses/investigations/hyperliquid-jelly-attack-context-vulnerability-team-solution), [Halborn: POPCAT November 2025](https://www.halborn.com/blog/post/explained-the-hyperliquid-hack-november-2025)

Five major margin-system incidents in 2025:
1. **ETH March 2025**: 50x leverage, $200M position, forced HLP to absorb $4M loss
2. **JELLY March 2025**: Position inheritance to HLP, $13.5M unrealized loss, protocol manually delisted at $0.0095
3. **XPL August 2025**: Isolated oracle exploit, $60M liquidations
4. **October 2025**: Flash crash, $10B in forced closures on Hyperliquid alone
5. **POPCAT November 2025**: 19-wallet coordination, $4.9M bad debt

**Remediation**: Max leverage reduced (40x BTC, 25x ETH), dynamic margin tiers launched May 2025, portfolio margin with caps.

### 6. Glassnode Validation — Independent Hyperliquid Liquidation Maps (Triangulated: 2 sources)

**Source**: [Glassnode: Liquidation Heatmaps](https://insights.glassnode.com/liquidation-heatmaps/)

Glassnode independently builds liquidation maps from Hyperliquid position-level data. They note:
- Hyperliquid accounts for ~16% of global OI
- "Liquidation zones observed on Hyperliquid show meaningful correlations with realized liquidations on larger exchanges"
- On-chain transparency enables reconstruction impossible on CEXs

This validates our approach direction but doesn't solve the reserved-margin formula gap.

---

## Candidate Reserved-Margin Formula (Derived from Documentation)

Based on Hyperliquid's documented behavior, the candidate formula for reserved margin per resting order:

```
reserved_margin(order) = abs(order_size) * order_price / leverage_at_placement
```

But this is the INITIAL check. The actual current reserved margin should be:

```
current_reserved(order) = abs(order_size) * mark_price / current_max_leverage_for_tier(notional)
```

Where `notional = abs(order_size) * mark_price` and the tier determines the max leverage.

For **cross-margin accounts with existing positions**, the reserved margin must also account for:
- Whether the order **increases** or **decreases** existing exposure (reducing orders may require zero additional margin)
- The **net** effect on account-level IM after the order fills
- Off-target orders that reserve margin from the same cross collateral pool

**Proposed test approach**: Compare `sum(candidate_reserved_margin)` for all resting orders of outlier users against their observed `margin_gap_total` from the existing drill-down data.

---

## Consumer Checkpoint Design Principles

Based on Cosmos/Tendermint patterns adapted for our consumer layer:

1. **Periodic snapshots**: Archive ABCI state for target-relevant users at ~15min cadence (reuse existing `periodic_abci_states`)
2. **Compact format**: Only retain relevant users (59k with positions, not full 1.4M) — estimated ~50-100MB per checkpoint vs 1.1GB full
3. **Deterministic**: Checkpoint keyed by block number, reproducible
4. **7d retention**: Consumer-owned, independent of producer's 2d rolling window
5. **Incremental replay**: Between checkpoints, replay `node_fills_by_block` + `node_order_statuses_by_block` for path-exactness

---

## PMW: Prove Me Wrong — Hostile Review

### Strengths
- **Solver correctness verified**: 0.02% error vs Hyperliquid live API for whale positions
- **Full-population coverage**: 339k-455k accounts vs CoinGlass's 153-285 top positions
- **Observable order state**: 4,636 resting orders reconstructed from retained feeds for 370 users
- **Off-target awareness**: Consumer code correctly identifies $117M off-target exposure for ETH-relevant accounts
- **Architecture boundary**: Clean separation between hyperliquid-node (producer) and sidecar (consumer)

### Weaknesses

**W1: Reserved-margin formula is a BLACK BOX**
- Hyperliquid does NOT publish the exact reserved-margin calculation
- The clearinghouse source is closed-source
- Our candidate formula `size * mark / leverage` is a guess based on documentation
- The actual formula may include: order-type-specific adjustments, time-decay, dynamic leverage caps, portfolio-margin interactions
- **Severity: HIGH** — This is the core unsolved problem and we cannot derive it from first principles

**W2: No academic precedent to validate against**
- Zero formal papers on perp exchange reserved-margin reconstruction
- No benchmarking methodology exists in literature
- We are operating entirely on reverse-engineering
- **Severity: MEDIUM** — Means our approach can't be peer-validated

**W3: 2-day ABCI retention is a hard constraint**
- True 7d analysis requires consumer-owned persistence that doesn't exist yet
- Each snapshot is ~1.1GB; 7 days at 15min cadence = ~670 snapshots = ~740GB
- Even compact (target-users-only) may be 50-100MB * 670 = 33-67GB
- **Severity: HIGH** — Blocks production 7d reproducibility

**W4: Portfolio margin changes the game**
- March 2026 alpha rollout introduces fundamentally different margin semantics
- Portfolio-margin accounts have net-risk-based collateral, not per-position IM
- Sidecar solver currently assumes standard cross-margin only
- We have no detection of which accounts are on portfolio margin
- **Severity: HIGH** — Could silently produce wrong liquidation prices for institutional accounts

**W5: Carry-in state is structurally unbounded**
- Orders placed before the retained-feed window cannot be reconstructed
- The bounded parser only sees orders with events in the retained window
- For 2-day retention, any order placed 3+ days ago and still resting is invisible
- This systematically underestimates reserved margin for patient limit orders
- **Severity: MEDIUM** — Biases results toward underestimating margin reserve

**W6: Margin system is a MOVING TARGET**
- Five major margin-system changes in 2025 alone (leverage limits, dynamic tiers, portfolio margin)
- Any reconstruction formula we derive today may be obsolete next month
- No versioning/changelog API for margin rules
- **Severity: MEDIUM** — Maintenance burden is permanently high

**W7: Mark price timing creates systematic error**
- ABCI snapshots are ~15min apart
- Between snapshots, mark can move significantly (BTC: 1% = $800+ at current prices)
- All liquidation prices are calculated at snapshot mark, not current mark
- For volatile periods (flash crashes), this error compounds
- **Severity: LOW-MEDIUM** — Bounded by snapshot cadence, not fundamental

**W8: The `M` field mystery remains unexplained**
- Snapshot `M` does not match solver MMR for most positions
- Outlier drill-down shows no single explanation pattern
- We may be missing entire accounting dimensions (e.g., insurance fund deductions, fee credits, referral rebates)
- **Severity: MEDIUM** — Indicates incomplete model of account state

### Opportunities

**O1: Hyperliquid API provides `clearinghouseState` per user**
- Could potentially query reserved margin directly for validation sample
- Compare API-reported values against our reconstruction
- May expose margin-mode detection (standard vs portfolio)

**O2: Glassnode independently validates the approach**
- They build liquidation maps from Hyperliquid data
- Their methodology could be compared/triangulated
- They represent ~16% of global OI coverage as a benchmark

**O3: Multi-snapshot differential analysis**
- Compare same user across consecutive snapshots
- Detect margin changes not explained by fills/funding
- Could reveal hidden margin mechanics

### Threats

**T1: CoinGlass comparison is structurally meaningless**
- Different populations make shape metrics uninformative
- Continued comparison effort has negative ROI
- Risk of overfitting to match CoinGlass's whale-only view

**T2: Hyperliquid could change ABCI snapshot format**
- No stability guarantee on internal state format
- msgpack schema already has quirks (the pytest-cov exception anomaly)
- Breaking change could invalidate entire consumer pipeline

**T3: Computational cost of full 7d analysis is prohibitive**
- 670 snapshots * 1.1GB = read 740GB of msgpack data
- Even streaming decode, this is hours of CPU time
- May need to sample rather than scan all snapshots

**T4: False precision trap**
- Displaying a liquidation heatmap with wrong reserved-margin assumptions gives a false sense of accuracy
- Users making trading decisions based on incorrect liquidation levels
- Worse than no map at all if systematically biased

### Mitigations

| Threat/Weakness | Mitigation | Status |
|-----------------|------------|--------|
| W1: Black-box formula | API validation against `clearinghouseState` | NOT STARTED |
| W3: 2d retention | Consumer checkpoint with compact format | DESIGN ONLY |
| W4: Portfolio margin | Detect margin mode from snapshot fields | NOT STARTED |
| W5: Carry-in | Multi-file window expansion | DESIGN ONLY |
| T1: CoinGlass trap | Accept best-effort, stop chasing shape match | DECIDED |
| T2: Schema break | Pin decoder to known-good snapshot version | NOT STARTED |
| T4: False precision | Add confidence bands / uncertainty markers to output | NOT STARTED |

### PMW Verdict: **WAIT**

**Justification**: The solver is mathematically correct for KNOWN state (verified 0.02% vs API). But the reserved-margin formula is entirely unvalidated, portfolio margin changes are imminent, and 7d production requires infrastructure that doesn't exist. Proceeding to "production" liquidation maps without solving the reserved-margin gap would present false precision to users.

**Recommended before GO**:
1. Validate candidate reserved-margin formula against Hyperliquid API `clearinghouseState` for 10+ outlier users
2. Detect and handle portfolio-margin accounts
3. Implement consumer checkpoint with at least 7d retention
4. Add uncertainty/confidence markers to output surfaces

---

## Confidence Scoring

**Overall: 72/100**

| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Source Agreement | 7/10 | 40% | 2.8 |
| Source Quality | 8/10 | 30% | 2.4 |
| Coverage Depth | 7/10 | 20% | 1.4 |
| Counter-Evidence | 6/10 | 10% | 0.6 |
| **Total** | | | **7.2** |

Gaps:
- No academic sources for reserved-margin formula (kills triangulation on P1)
- Portfolio margin documentation still evolving
- Hyperliquid clearinghouse source code closed

---

## Research Metrics

```
Iterations: 2 (search + hostile)
PePeRS runs: 2 (run-20260324-121349-d28283, run-20260324-121349-472659)
PePeRS relevant papers: 0 (confirms academic gap)
Web searches: 8
Sources searched: 15+
Cache: MISS (first run)
```

---

## Sources

**Hyperliquid Official Docs:**
- [Margining](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margining)
- [Margin Tiers](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margin-tiers)
- [Liquidations](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations)
- [Portfolio Margin](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/portfolio-margin)
- [Order Book](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/order-book)

**Exploit Post-Mortems:**
- [Halborn: ETH Hack March 2025](https://www.halborn.com/blog/post/explained-the-hyperliquid-hack-march-2025)
- [OAK Research: JELLY Attack](https://oakresearch.io/en/analyses/investigations/hyperliquid-jelly-attack-context-vulnerability-team-solution)
- [Halborn: POPCAT November 2025](https://www.halborn.com/blog/post/explained-the-hyperliquid-hack-november-2025)
- [Yahoo Finance: Third Attack](https://finance.yahoo.com/news/hyperliquid-hit-third-market-manipulation-113215395.html)

**Architecture / Checkpoint:**
- [Tendermint ADR-042: State Sync](https://github.com/tendermint/tendermint/blob/master/docs/architecture/adr-042-state-sync.md)
- [Tendermint ADR-053: State Sync Prototype](https://github.com/tendermint/tendermint/blob/master/docs/architecture/adr-053-state-sync-prototype.md)
- [Cosmos SDK Snapshots](https://pkg.go.dev/github.com/cosmos/cosmos-sdk/snapshots)
- [Jane Street: Building an Exchange](https://www.janestreet.com/tech-talks/building-an-exchange/)
- [How Exchanges Turn Order Books into Distributed Logs](https://quant.engineering/exchange-order-book-distributed-logs.html)

**Academic / Analysis:**
- [DeFi Liquidations Study](https://www.researchgate.net/publication/355838152_An_empirical_study_of_DeFi_liquidations_incentives_risks_and_instabilities)
- [Autodeleveraging: Impossibilities and Optimization](https://arxiv.org/html/2512.01112v2)
- [Glassnode: Liquidation Heatmaps](https://insights.glassnode.com/liquidation-heatmaps/)

**Portfolio Margin Updates:**
- [CoinDesk: Portfolio Margin Alpha](https://www.coindesk.com/markets/2026/03/10/hyperliquid-s-new-upgrade-to-let-traders-take-bigger-bets-with-less-capital)
- [PANews: Margin Upgrade](https://www.panewslab.com/en/articles/7yknq43m)

**Implementations:**
- [hyperliquid-dex/order_book_server](https://github.com/hyperliquid-dex/order_book_server)
- [mansoor-mamnoon/limit-order-book](https://github.com/mansoor-mamnoon/limit-order-book)
- [enewhuis/liquibook](https://github.com/enewhuis/liquibook)
