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
- [X] T017 Inventory the concrete local sources for mark/oracle, funding, and collateral/equity adjustments required by the chosen full-input path
  - **Available locally** (9 days: 2026-03-12 → 2026-03-20):
    - `node_fills_by_block/hourly/` — exact fill prices, sizes, directions (Close Long/Short for liquidations)
    - `node_order_statuses_by_block/hourly/` — order lifecycle including `filled` events with limitPx/sz
    - `node_raw_book_diffs_by_block/hourly/` — per-user book deltas at block granularity
    - `hip3_oracle_updates_by_block/hourly/` — mark_px + oracle_px per coin (BTC as `cash:BTC`, ETH as `hyna:ETH`)
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
      - `users_with_positions`: **59,596** active users
      - `asset_to_oi_szi`: aggregate OI per asset (BTC=2.85B szi, ETH=5.89B szi)
    - **Account equity is directly anchorable at snapshot times** from balances plus position/funding state; this is confirmed for the retained `2d` ABCI window
    - **Open proof item**: exact `7d` replay still needs to be demonstrated from snapshots + filtered streams across the full candidate window
  - **Maintenance margin rates** — Hyperliquid uses cross-margin with fixed 3% initial / 1% maintenance; no per-tier lookup needed
  - **Conclusion**: ALL major inputs for high-fidelity reconstruction are locally available, but the certainty level differs: `2d` is snapshot-anchored, while exact `7d` replay remains to be proven

## Phase 4: Reconstruction Design

- [X] T018 Document which quantities are `snapshot-exact`, `replay-exact`, `approximate`, or still not reconstructable from local data, and tie that envelope to the chosen sidecar-vs-node boundary
- [X] T019 Choose the first reconstruction target: `position-state reconstruction`
  - Rationale: exact BTC/ETH parity for multi-asset cross-margin accounts requires account-level state; cohort-only approximations are insufficient
- [X] T020 Define the sidecar retained account-state format so BTC/ETH-relevant accounts keep the off-target exposure needed for exact cross-margin liquidation semantics
- [X] T021 Define bucket size, accumulation metric, and side split for the first `ETH` builder
- [X] T022 Record the current retention constraint explicitly: immediate comparison windows are `1d` and `7d`, not `30d+`, while ABCI anchors are only confirmed locally for `2d`
- [X] T023 Write a short sidecar design note for the first prototype builder, including the minimal generic `hyperliquid-node` changes allowed, if any

## Phase 5: ETH Prototype Builder

- [ ] T024 Implement the first local `ETH 7d` prototype builder
- [ ] T025 Generate a local `ETH 7d` risk-surface artifact from filtered node data
- [ ] T026 Compare the prototype against CoinGlass Hyperliquid `ETH` on peak buckets, shape, and long/short balance
- [ ] T027 Run an `ETH 1d` sensitivity pass to measure sparsity and stability

## Phase 6: BTC Extension And Decision

- [ ] T028 Extend the same reconstruction path to `BTC`
- [ ] T029 Write a Rektslug-vs-CoinGlass Hyperliquid comparison memo for `BTC` and `ETH`
- [ ] T030 Record whether `1:1` Hyperliquid parity is viable, best-effort only, or rejected
- [ ] T031 Document repeatable capture, decode, and comparison commands for future reruns

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
  - timeframe still unresolved, but payload-level `1 day` vs `7 day` split is not visible
  - simple recent-liquidation histograms are not sufficient to explain CoinGlass Hyperliquid
- Reconstruction-input decision:
  - the target high-fidelity path should include mark/oracle, funding, and collateral/equity adjustments in addition to fills, order statuses, and raw book diffs
  - exact BTC/ETH parity must preserve account-level cross-margin semantics even when the relevant wallets hold off-target assets
- Architecture decision:
  - implement the BTC/ETH parity/reconstruction engine as a sidecar over canonical node outputs
  - keep `hyperliquid-node` limited to canonical collection/filtering/state export responsibilities, with only generic infrastructure changes allowed if the sidecar proves they are needed
- Phase 4 design artifact:
  - `specs/026-liqmap-model-calibration/sidecar-design.md` defines the exactness envelope, relevant-account rule, retained account state, replay proof rules, and the minimal allowed node-side changes
  - the same design note also fixes the first builder parameters: profile-resolved bin size, target-notional accumulation, and side split from target-position sign
