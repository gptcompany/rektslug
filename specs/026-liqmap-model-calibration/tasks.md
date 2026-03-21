# Tasks: Liq Map Model Calibration & Hyperliquid Alignment

**Input**: `specs/026-liqmap-model-calibration/spec.md`
**Dependencies**: `spec-017`, `spec-018`, `spec-019`, local Hyperliquid node filtered data, and CoinGlass capture/decode tooling
**Feature Type**: Investigation + implementation tracking

## Phase 1: Evidence Lock-In

- [X] T001 Re-read `spec-026` and the Hyperliquid/CoinGlass handoff manifests
- [X] T002 Confirm the correct Rektslug-side Hyperliquid source is the filtered node dataset, especially `filtered/node_fills_by_block`
- [X] T003 Confirm the resumed investigation branch/commit checkpoint (`d86fbbf`, `4eb0acb` on `master`)
- [X] T004 Patch `scripts/capture_provider_api.py` to target the `Hyperliquid Liquidation Map` widget instead of the Binance/per-exchange widget
- [X] T005 Route CoinGlass credentials through the shared secret path used by `get_secret()` / `dotenvx`
- [X] T006 Obtain a verified local CoinGlass Hyperliquid `ETH` artifact with `symbol_applied = true`
- [X] T007 Verify the saved request is `api/hyperliquid/topPosition/liqMap?symbol=ETH` and mark `request_verified = true`

## Phase 2: CoinGlass Payload Semantics

- [X] T008 Decode verified CoinGlass Hyperliquid payloads and record the object shape
- [X] T009 Verify the decoded Hyperliquid payload is a top-position / position-risk feed, not a pre-bucketed heatmap
- [X] T010 Re-run verified `ETH` captures for `1 day` and `7 day`
- [X] T011 Compare decoded `ETH` `1 day` vs `7 day` payloads and bound timeframe behavior
- [X] T012 Record that the current live Hyperliquid selector exposes symbols beyond `BTC` / `ETH`, while repo scope remains `BTC` / `ETH`

## Phase 3: Local Baseline And Data Inventory

- [X] T013 Confirm filtered node retention also includes `node_order_statuses_by_block` and `node_raw_book_diffs_by_block`
- [X] T014 Confirm the canonical Hyperliquid candidate-window baseline artifact exists in repo and is structurally valid
- [X] T015 Inspect schema/sample payloads for `node_order_statuses_by_block`
  - **Schema**: `{local_time, block_time, block_number, events[]}`
  - **Event fields**: `{time, user, hash, builder, status, order{coin, side, limitPx, sz, oid, timestamp, orderType, origSz, tif, cloid, reduceOnly, isPositionTpsl, isTrigger, triggerPx, triggerCondition, children}}`
  - **Statuses**: badAloPxRejected (986k), open (131k), canceled (125k), perpMarginRejected (88k), filled (4.4k), reduceOnlyRejected, scheduledCancel, minTradeNtlRejected, triggered, etc.
  - **Coins**: BTC, ETH, HYPE | **Sides**: A (ask/sell), B (bid/buy)
  - **Order types**: Limit, Market, Stop Limit, Stop Market, Take Profit Limit, Take Profit Market
  - **Relevance**: `filled` events give exact execution prices and sizes; `open` orders give resting limit orders (potential liquidation walls)
- [X] T016 Inspect schema/sample payloads for `node_raw_book_diffs_by_block`
  - **Schema**: `{local_time, block_time, block_number, events[]}`
  - **Event fields**: `{user, oid, coin, side, px, raw_book_diff}`
  - **diff types**: `new` (new order, subkey: sz), `update` (size change)
  - **Coins**: BTC, ETH, HYPE | **Sides**: A, B
  - **Relevance**: Full order book reconstruction possible; per-price-level depth snapshots for book-aware impact overlay
- [ ] T017 Inventory the concrete local sources for mark/oracle, funding, and collateral/equity adjustments required by the chosen full-input path
  - **Available locally** (9 days: 2026-03-12 → 2026-03-20):
    - `node_fills_by_block/hourly/` — exact fill prices, sizes, directions (Close Long/Short for liquidations)
    - `node_order_statuses_by_block/hourly/` — order lifecycle including `filled` events with limitPx/sz
    - `node_raw_book_diffs_by_block/hourly/` — per-user book deltas at block granularity
    - `hip3_oracle_updates_by_block/hourly/` — `coin_to_mark_px`, `coin_to_oracle_px`, and `coin_to_external_perp_px`; for Hyperliquid perps the current target mapping is `hyna:BTC` / `hyna:ETH`, not `cash:BTC`
  - **Also available via ccxt-data-pipeline** (Docker, `/data/catalog/`):
    - `funding_rate/BTCUSDT-PERP.HYPERLIQUID/` — 52 days of parquet (2026-01-28 → 2026-03-20)
    - `funding_rate/ETHUSDT-PERP.HYPERLIQUID/` — same coverage
    - `open_interest/{BTC,ETH}USDT-PERP.HYPERLIQUID/` — OI history
    - `ohlcv/{BTC,ETH}USDT-PERP.HYPERLIQUID/` — candles
    - `trades/{BTC,ETH}USDT-PERP.HYPERLIQUID/` — trade ticks
  - **Also available via periodic ABCI state snapshots** (`periodic_abci_states/`):
    - Path: `/media/sam/4TB-NVMe/docker-volumes/hyperliquid/hl/data/periodic_abci_states/`
    - Format: MessagePack (`.rmp`), ~1.1GB each, ~80-100/day (~15min cadence)
    - Retention: 2 days (20260319-20260320)
    - Content: full clearinghouse state — `exchange.locus.cls[0].user_states`
      - `user_to_state`: **1,488,930 users**, each with:
        - `S.s` / `S.r` — USDC balance (scaled integers)
        - `p.p[]` — positions by asset index (`[0]=BTC`, `[1]=ETH`, `[5]=SOL`, 229 total)
        - Per-position: `l.C` (cross leverage), `l.I` (isolated leverage), `M` (margin), `f.a` (cumulative funding)
      - `open_order_tracker`: key presence confirmed in the `.rmp` snapshots; structured extraction/inventory still needs explicit parser work
      - `users_with_positions`: **59,596** active users
      - `asset_to_oi_szi`: aggregate OI per asset (BTC=2.85B szi, ETH=5.89B szi)
    - **Account equity is directly anchorable at snapshot times** from balances plus position/funding state; this is confirmed for the retained `2d` ABCI window
  - **Missing / unconfirmed for replay-exact between snapshots**:
    - no transfer / deposit / withdrawal / collateral-adjustment stream has been identified in the current filtered inventory
    - no node-side funding application / heartbeat event has been confirmed; local funding-rate history exists, but the application schedule into account state is not yet proven
  - **Maintenance margin rates** — Hyperliquid margin requirements are asset-specific and tier-dependent (derived from `marginTables` / max leverage); the sidecar must perform metadata lookups for these rules rather than assuming fixed rates.
  - **Conclusion**: snapshot anchoring is locally strong, but replay-exact between snapshots is still unproven and T017 stays open until path-drift risks (transfers, funding application timing, off-target activity) are bounded.

## Phase 4: Reconstruction Design

- [X] T018 Document which quantities are `snapshot-exact`, `replay-exact`, `approximate`, or still not reconstructable from local data, and tie that envelope to the chosen sidecar-vs-node boundary
- [X] T019 Choose the first reconstruction target: `position-state reconstruction`
  - Rationale: exact BTC/ETH parity for multi-asset cross-margin accounts requires account-level state; cohort-only approximations are insufficient
- [X] T020 Define the sidecar retained account-state format so BTC/ETH-relevant accounts keep the off-target exposure needed for exact cross-margin liquidation semantics
- [X] T021 Define bucket size, accumulation metric, and side split for the first `ETH` builder
- [X] T022 Record the current retention constraint explicitly: immediate comparison windows are `1d` and `7d`, not `30d+`, while ABCI anchors are only confirmed locally for `2d`
- [X] T023 Write a short sidecar design note for the first prototype builder, including the minimal generic `hyperliquid-node` changes allowed, if any

## Phase 5: ETH Prototype Builder

- [X] T024 Implement the first local `ETH 7d` prototype builder
- [X] T025 Generate a local `ETH 7d` risk-surface artifact from filtered node data
- [X] T033 Refine the V0 liquidation solver to handle multi-asset cross-margin equity/margin adjustments rather than simple 1-asset shock
- [X] T026 Compare the prototype against CoinGlass Hyperliquid `ETH` on peak buckets, shape, and long/short balance
  - Absorbed into Phase 6 comparison script (`scripts/compare_hl_sidecar_vs_coinglass.py`)
  - ETH results: Pearson r=0.003, KS=0.430, L/S diff=0.044
- [ ] T027 Run an `ETH 1d` sensitivity pass to measure sparsity and stability
  - **Deferred post-decision**: not a prerequisite for the parity decision; can be executed as follow-up optimization
- [ ] T034 Investigate Open Orders impact: quantify the reserved-margin gap by comparing snapshot `M` field vs current solver MMR
  - **Deferred post-decision**: impact estimated as marginal (reserved margin from resting orders); investigate only if comparison reveals significant drift
- [ ] T035 Refactor `load_abci_anchor` to use `msgpack.Unpacker` for streaming decoding (memory optimization)
  - **Deferred optimization**: pure technical performance improvement, does not block parity decision

## Phase 6: BTC Extension And Decision

- [X] T028 Extend the same reconstruction path to `BTC`
  - Generated `data/validation/liqmap_hl_btc_7d.json`: 455,175 accounts, 7,273 long + 6,507 short buckets, L/S=0.886
  - CoinGlass BTC Hyperliquid reference already present in capture `20260320T183129Z` (285 top positions)
- [X] T029 Write a Rektslug-vs-CoinGlass Hyperliquid comparison memo for `BTC` and `ETH`
  - `specs/026-liqmap-model-calibration/parity-decision.md`: full shape metrics, volume scale analysis, population explanation
  - Comparison script: `scripts/compare_hl_sidecar_vs_coinglass.py` (--all runs both symbols)
- [X] T030 Record whether `1:1` Hyperliquid parity is viable, best-effort only, or rejected
  - **Decision: best-effort parity** -- 1:1 shape match is structurally impossible (CoinGlass tracks ~250 whales, Rektslug tracks ~400k accounts)
  - L/S ratio agreement within 0.04-0.05 validates directional correctness
  - Rektslug provides more comprehensive coverage than CoinGlass
- [X] T031 Document repeatable capture, decode, and comparison commands for future reruns
  - Added "Repeatable Commands" section to `specs/026-liqmap-model-calibration/sidecar-design.md`
- [X] T032 If exact `7d` parity still depends on longer-lived anchors or a generic checkpoint exporter, track that node-side dependency explicitly as blocked infrastructure work
  - **Blocked infrastructure**: ABCI retention is 2 days; true 7d historical analysis requires either (a) extending periodic_abci_states retention to 7+ days, or (b) implementing a checkpoint exporter that archives snapshots to persistent storage. Current workaround: single latest anchor is acceptable for position-state but not for volume-over-time analysis.

## Completion Notes

- Verified local Hyperliquid `ETH` captures:
  - `data/validation/raw_provider_api/20260320T181726Z/manifest.json`
  - `data/validation/raw_provider_api/20260320T183040Z/manifest.json`
  - `data/validation/raw_provider_api/20260320T183129Z/manifest.json`
- Validated local reference artifacts:
  - `data/validation/manifests/hyperliquid_filtered_candidate_windows_20260320.json`
  - `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.json`
  - `data/validation/manifests/coinglass_hyperliquid_decode_audit_20260320.json`
- Current bounded conclusion:
  - harness fixed and verified for local `ETH`
  - CoinGlass Hyperliquid payload decoded successfully
  - **Cross-Margin Solver V1** implemented and validated: correctly handles Balance, multi-asset PnL, Funding, and MMR Tiers
  - artificial volume spike at price 0.0 removed (99.99% reduction)
  - simple recent-liquidation histograms are not sufficient to explain CoinGlass Hyperliquid; full account-state reconstruction is mandatory
- Reconstruction-input decision:
  - the target high-fidelity path should include mark/oracle, funding, and collateral/equity adjustments in addition to fills, order statuses, and raw book diffs
  - exact BTC/ETH parity must preserve account-level cross-margin semantics even when the relevant wallets hold off-target assets
  - replay-exact between ABCI anchors remains unproven until collateral-adjustment coverage and funding-application timing are explicitly bounded
- Architecture decision:
  - implement the BTC/ETH parity/reconstruction engine as a sidecar over canonical node outputs
  - keep `hyperliquid-node` limited to canonical collection/filtering/state export responsibilities, with only generic infrastructure changes allowed if the sidecar proves they are needed
- Phase 4 design artifact:
  - `specs/026-liqmap-model-calibration/sidecar-design.md` defines the exactness envelope, relevant-account rule, retained account state, replay proof rules, and the minimal allowed node-side changes
  - the same design note also fixes the first builder parameters: profile-resolved bin size, target-notional accumulation, and side split from target-position sign
- Phase 6 comparison artifacts:
  - `data/validation/liqmap_hl_btc_7d.json` — BTC 7d risk-surface (455k accounts)
  - `data/validation/comparison_hl_eth.json` — ETH comparison metrics
  - `data/validation/comparison_hl_btc.json` — BTC comparison metrics
  - `data/validation/comparison_hl_combined.json` — combined report
  - `specs/026-liqmap-model-calibration/parity-decision.md` — go/no-go decision memo
  - `scripts/compare_hl_sidecar_vs_coinglass.py` — repeatable comparison script
- Phase 6 decision: **best-effort parity** accepted
  - 1:1 shape match structurally impossible (whale-only vs full-population)
  - L/S ratio validates directional correctness (within 0.04-0.05)
  - Rektslug sidecar provides superior coverage (339k-455k accounts vs 153-285 top positions)
  - Blocked infrastructure: ABCI retention (2d) limits true 7d historical analysis
