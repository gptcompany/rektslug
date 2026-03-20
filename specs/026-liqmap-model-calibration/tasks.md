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
- [ ] T015 Inspect schema/sample payloads for `node_order_statuses_by_block`
- [ ] T016 Inspect schema/sample payloads for `node_raw_book_diffs_by_block`
- [ ] T017 Inventory the concrete local sources for mark/oracle, funding, and collateral/equity adjustments required by the chosen full-input path

## Phase 4: Reconstruction Design

- [ ] T018 Document which quantities are exact, approximate, or not reconstructable from local data
- [ ] T019 Choose the first reconstruction target: `position-state reconstruction`, `position-cohort risk surface`, or `book-aware impact overlay`
- [ ] T020 Define bucket size, accumulation metric, and side split for the first `ETH` builder
- [ ] T021 Record the current retention constraint explicitly: immediate comparison windows are `1d` and `7d`, not `30d+`
- [ ] T022 Write a short design note for the first prototype builder and its validation metrics

## Phase 5: ETH Prototype Builder

- [ ] T023 Implement the first local `ETH 7d` prototype builder
- [ ] T024 Generate a local `ETH 7d` risk-surface artifact from filtered node data
- [ ] T025 Compare the prototype against CoinGlass Hyperliquid `ETH` on peak buckets, shape, and long/short balance
- [ ] T026 Run an `ETH 1d` sensitivity pass to measure sparsity and stability

## Phase 6: BTC Extension And Decision

- [ ] T027 Extend the same reconstruction path to `BTC`
- [ ] T028 Write a Rektslug-vs-CoinGlass Hyperliquid comparison memo for `BTC` and `ETH`
- [ ] T029 Record whether `1:1` Hyperliquid parity is viable, best-effort only, or rejected
- [ ] T030 Document repeatable capture, decode, and comparison commands for future reruns

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
