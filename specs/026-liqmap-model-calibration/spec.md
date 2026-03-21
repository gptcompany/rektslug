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

**Important CoinGlass scope distinction**:
- CoinGlass exposes multiple liquidation map views on the same product page, and
  they are NOT interchangeable:
  1. Per-exchange view (for example `Binance_BTCUSDT`, `Binance_ETHUSDT`)
  2. Aggregated exchange view (`BTC`, `ETH` across exchanges)
  3. Hyperliquid-specific view (`BTC`, `ETH`) via a separate endpoint
- For this spec, Binance was selected as the CoinGlass reference for convenience
  and comparability with our current public builder. This is an exchange-specific
  comparison, not an aggregate-market comparison.
- Do not compare Rektslug/CoinGlass Binance-style results against the CoinGlass
  aggregated view. They are different datasets with different semantics.

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

#### P5: Investigate CoinGlass Hyperliquid Parity
- Treat CoinGlass Hyperliquid as a separate dataset from both the CoinGlass
  per-exchange liq map and the CoinGlass aggregated exchange liq map
- Investigate `api/hyperliquid/topPosition/liqMap?symbol=BTC|ETH` separately from
  `index/5/liqMap` and `index/2/exLiqMap` flows
- Determine what CoinGlass means by Hyperliquid symbols `BTC` and `ETH`
  (likely perp/futures-oriented, but do not assume exact contract semantics
  without evidence)
- Determine whether CoinGlass Hyperliquid uses a fixed, implicit, or
  server-side timeframe, since the page does not expose one visually for that
  section
- Compare Rektslug Hyperliquid candidate windows against CoinGlass Hyperliquid
  BTC/ETH only after symbol semantics and timeframe assumptions are bounded
- For BTC/ETH parity, preserve exact account-level cross-margin semantics even
  when the relevant accounts also hold non-BTC/ETH positions; dropping those
  off-target exposures is explicitly out of bounds for the parity path
- Implement the reconstruction/parity engine as a sidecar over the canonical
  node outputs, not as BTC/ETH-specific business logic inside
  `hyperliquid-node`
- Limit any `hyperliquid-node` changes to generic infrastructure support only
  (for example retention/export of state anchors or a generic derived
  checkpoint), not CoinGlass-specific or parity-specific modeling logic
- Produce an explicit decision on whether 1:1 Rektslug vs CoinGlass
  Hyperliquid parity is supportable or only best-effort

### Out of Scope
- Real-time CoinGlass data (encrypted, requires periodic bundle refresh)
- Matching CoinAnK exactly (no ground truth, different methodology)
- Shipping a production Hyperliquid CoinGlass parity mode before symbol
  semantics and timeframe behavior are verified
- New frontend views (defer to spec-025 WebSocket)

### Open Questions
- What exactly do CoinGlass Hyperliquid symbols `BTC` and `ETH` represent?
  They likely refer to Hyperliquid perp/futures-oriented markets, but the
  exact contract semantics should not be assumed without evidence from payloads,
  docs, or repeatable capture behavior.
- What timeframe or lookback window does CoinGlass Hyperliquid use for
  `api/hyperliquid/topPosition/liqMap`? The page exposes no visible timeframe
  selector for that section, unlike the per-exchange and aggregated liq-map
  sections.
- Is the Hyperliquid timeframe fixed, symbol-specific, account-tier-specific,
  or server-derived from another hidden state on the page?
- Can Rektslug derive a comparable Hyperliquid map from our L4/node data using
  a bounded candidate set of windows, or does CoinGlass use additional vendor
  inputs we cannot infer?
- Are CoinGlass Hyperliquid BTC/ETH maps based on liquidation risk for current
  open positions, recently closed positions, top-position cohorts, or another
  provider-specific construction?
- What is the smallest derived account-state representation that still preserves
  exact BTC/ETH liquidation semantics for multi-asset cross-margin accounts?


### Findings To Date
- F-001: The correct Rektslug-side source for Hyperliquid discovery is the
  filtered node dataset, especially `filtered/node_fills_by_block`, not only
  the derived DuckDB views. The node docs describe this dataset as `fills +
  liquidations`, and `scripts/ingest_hl_fills.py` already converts it into
  `hl_fills_l4` / `hl_liquidations_l4`.
- F-002: The local CoinGlass browser harness is now a verified Hyperliquid
  `ETH` capture path. Verified runs `20260320T181726Z`, `20260320T183040Z`,
  and `20260320T183129Z` all recorded `login_attempted = true`,
  `login_success = true`, `symbol_applied = true`, and
  `request_verified = true`, and saved
  `api/hyperliquid/topPosition/liqMap?symbol=ETH`.
- F-003: The CoinGlass browser automation is no longer coupled only to the
  main per-exchange/Binance widget. `scripts/capture_provider_api.py` now has
  a Hyperliquid-specific widget-selection path, and CoinGlass credentials load
  through the shared secret path (`get_secret()` / `dotenvx`) rather than only
  through ad hoc shell environment injection.
- F-004: Decoded CoinGlass Hyperliquid payloads are not shaped like a
  pre-bucketed heatmap. Successful decodes yield an object with top-level keys
  `price` and `list`, and list items include fields such as `entryPrice`,
  `leverage`, `liquidationPrice`, `margin`, `positionUsd`, `size`, and
  `userId`. Inference: the endpoint currently looks closer to a top-position /
  position-risk feed than to a ready-made liquidation surface.
- F-005: CoinGlass Hyperliquid timeframe behavior remains unresolved, but the
  verified `ETH` `1 day` and `7 day` runs decode to the same logical object
  shape, the same `153` IDs, and no explicit timeframe field. The remaining
  differences look like live mark-to-market updates rather than two distinct
  historical windows.
- F-006: Rektslug-side candidate windows for immediate testing remain `1d` and
  `7d`, and current local node retention only supports roughly `7d` of history.
  `7d` already produces a much richer `ETH` distribution than `1d`, so it is
  the correct first prototype window. This is still a candidate, not evidence
  that CoinGlass actually uses `7d`.
- F-007: Current evidence argues against the hypothesis that CoinGlass
  Hyperliquid is based only on public `L2` websocket data. The decoded payload
  contains account/position-level fields such as `margin`, `leverage`, and
  `liquidationPrice`, which are not explained by plain order-book depth alone.
  This is still an inference, not a confirmed statement about CoinGlass
  internals.
- F-008: The filtered Hyperliquid dataset also retains
  `node_order_statuses_by_block` and `node_raw_book_diffs_by_block`, and local
  periodic ABCI snapshots provide direct per-user clearinghouse state anchors
  (balances, positions, margin/funding fields) for `20260319-20260320`. For
  the target high-fidelity reconstruction path, mark/oracle, funding, and
  collateral/equity adjustments should be treated as required inputs rather
  than optional refinements.
- F-009: The strongest hard local reconstruction claim is currently
  `snapshot-exact at retained ABCI anchor times over ~2d`, not replay-exact
  across the full `~2d` window and not proven exact for `7d`. Extending this
  to replay-exact requires proof that collateral adjustments, funding
  application timing, and other balance-moving events are fully observed
  between anchors.
- F-010: A preliminary `ETH` comparison shows no overlap between CoinGlass
  bucketized `liquidationPrice` peaks from the top-position feed and Rektslug
  `1d` / `7d` peaks derived from recent liquidation events. Therefore a simple
  histogram of recent liquidations is not sufficient to explain CoinGlass
  Hyperliquid.
- F-011: The required parity target has now been tightened: BTC/ETH parity
  must remain exact even for accounts that also hold off-target assets under
  cross-margin. Therefore any model that drops non-BTC/ETH exposures from those
  accounts is unacceptable for the parity path.
- F-012: For our node data, stronger candidate models than a simple histogram
  of recent liquidations are:
  1. position-state reconstruction
  2. position-cohort risk surface
  3. book-aware impact overlay
  These are modeling directions for future work, not yet implemented features.
- F-013: The implementation boundary should keep `hyperliquid-node` as the
  canonical collection/state source and move the parity/risk-surface builder
  into a sidecar. This keeps BTC/ETH- and CoinGlass-specific reconstruction
  logic out of the node while still allowing generic node-side retention/export
  improvements if they become necessary.
- F-014: Current local inventory does not yet identify a transfer / deposit /
  withdrawal / collateral-adjustment stream, and the node docs mark funding
  rate signals as missing from the core filtered outputs. Local funding-rate
  history exists via `ccxt-data-pipeline`, but the exact node-side funding
  application schedule is still unproven. Therefore replay-exact claims between
  anchors must remain bounded until those gaps are explicitly closed or shown
  to be zero-drift at re-anchor time.
- F-015: ABCI snapshot math confirmed: field `e` is **Total Position Cost** (scaled `1e6` USDC), not Entry Price. Token size `s` uses `szDecimals` from universe metadata. Formula `entry_px = (e / 1e6) / abs(size_scaled)` produces accurate price-levels and volumes consistent with Open Interest.
- F-016: ABCI MessagePack structure confirmed: massive collections like `user_to_state` and position lists `p.p` are encoded as **lists of pairs** `[[key, val], ...]` rather than native maps, requiring sequential iteration for decoding.
- F-017: Cross-Margin Solver V1 successfully integrated: by calculating `AccountValue = Balance + sum(PnL) - Funding` and `MMR = sum(Notional * Rate - Deduction)`, the solver correctly filters unliquidatable accounts (liq_price <= 0), reducing the artificial volume spike at price 0.0 by 99.99%.

### Investigation Plan
- IP-001: Build an evidence matrix for CoinGlass Hyperliquid `BTC` and `ETH`
  captures. For each capture, record request URL, headers, decoded payload
  structure, visible UI state, and whether any page-level timeframe change
  affects the Hyperliquid endpoint.
- IP-002: Investigate symbol semantics. Compare CoinGlass Hyperliquid `BTC` and
  `ETH` payload fields against Hyperliquid market naming, contract metadata,
  and any page labels to determine whether the maps refer to perp/open-interest
  risk, top-position cohorts, or another construction.
- IP-003: Investigate timeframe behavior. Re-run captures while changing the
  main page timeframe, reloading sessions, and varying symbol selection to test
  whether `api/hyperliquid/topPosition/liqMap` is fixed, implicit, or tied to
  hidden state.
- IP-003a: Identify whether the local node/exported datasets include
  collateral-adjustment events and an explicit funding-application signal. If
  either remains missing, bound the parity path as snapshot-anchored rather
  than replay-exact between anchors.
- IP-004: Generate Rektslug Hyperliquid candidate maps from our L4/node data
  for the windows currently supported by local retention, at minimum `1d` and
  `7d` today, so CoinGlass can be compared against concrete alternatives
  instead of a single guessed window. Expand to `14d` / `30d` only after the
  node retention window actually supports them. This sweep is for Hyperliquid
  timeframe discovery only.
- IP-004a: Keep canonical Binance/CoinAnK/CoinGlass comparisons on `1d` and
  `1w` (`7 day` in CoinGlass UI), rather than mixing them with the broader
  Hyperliquid discovery window sweep.
- IP-005: Compare CoinGlass Hyperliquid vs Rektslug candidate windows on shape,
  scale, L/S ratio, peak location, and stability over repeated captures for
  both `BTC` and `ETH`. For the exact-parity path, this comparison must be
  driven by account-level state that preserves off-target cross-margin
  exposures for the relevant accounts.
- IP-006: Record a final decision memo: either the inferred assumptions are
  strong enough to support a 1:1 Hyperliquid parity mode, or the feature stays
  explicitly best-effort.

### Expected Deliverables
- A capture manifest for CoinGlass Hyperliquid `BTC` and `ETH`, including raw
  request metadata and decoded payload summaries.
- A short symbol-semantics note describing what `BTC` and `ETH` most likely map
  to, plus any unresolved ambiguity.
- A timeframe-discovery note documenting what was tested, what changed, what did
  not change, and the bounded hypotheses that remain.
- A Rektslug-vs-CoinGlass comparison report covering the candidate windows and
  the metrics used to choose or reject them.
- A go/no-go parity recommendation for implementing Hyperliquid support in the
  public model layer.
- A sidecar architecture note that defines the boundary between
  `hyperliquid-node` and the parity/reconstruction engine, including which
  generic node-side exports are allowed and which modeling logic must remain
  outside the node.
- A concrete Phase 4 sidecar design artifact (`specs/026-liqmap-model-calibration/sidecar-design.md`) that defines the exactness envelope, retained account state, and replay proof rules.

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
- SC-006: CoinGlass Hyperliquid is documented as distinct from CoinGlass
  aggregated and per-exchange liq-map views
- SC-007: CoinGlass Hyperliquid symbol semantics for `BTC` and `ETH` are either
  identified with evidence or explicitly marked unresolved with bounded
  hypotheses
- SC-008: CoinGlass Hyperliquid timeframe behavior is either identified with
  evidence or explicitly marked unresolved with bounded hypotheses
- SC-009: Rektslug vs CoinGlass Hyperliquid comparison report exists for BTC and
  ETH using documented candidate windows/assumptions
- SC-010: Spec records a go/no-go decision for 1:1 Rektslug vs CoinGlass
  Hyperliquid parity
- SC-011: Any accepted BTC/ETH parity path preserves exact account-level
  cross-margin semantics for accounts with mixed-asset exposure, rather than
  approximating away the non-target side of those books
- SC-012: Any accepted implementation path keeps `hyperliquid-node` focused on
  canonical data/state collection, with the BTC/ETH parity engine implemented
  as a sidecar and any node changes limited to generic infrastructure support
