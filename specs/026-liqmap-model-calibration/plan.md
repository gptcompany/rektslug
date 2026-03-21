# Implementation Plan: Liq Map Model Calibration & Hyperliquid Alignment

**Spec**: `specs/026-liqmap-model-calibration/spec.md`
**Feature Type**: Investigation + implementation tracking
**Branch**: master

## Summary

`spec-026` has moved from generic multi-provider calibration into an active
Hyperliquid/CoinGlass discovery track. The immediate goal is to freeze the
current evidence, track what is already verified, and organize the next
implementation work required to build a credible Rektslug Hyperliquid
liquidation map from local node data. The parity target is now explicit: BTC
and ETH support must remain exact even for accounts that carry additional
non-target cross-margin exposure. The architectural boundary is also explicit:
`hyperliquid-node` stays the canonical data/state layer, while the parity and
risk-surface engine lives in a sidecar. This plan is intended to serve as the
current handoff index for continuing implementation in Claude.

## Technical Context

### Current State

- Verified local CoinGlass Hyperliquid `ETH` captures now exist and are saved
  under `data/validation/raw_provider_api/20260320T181726Z`,
  `20260320T183040Z`, and `20260320T183129Z`.
- Hyperliquid `1 day` vs `7 day` on CoinGlass does not currently expose a
  distinct historical timeframe at decoded payload level.
- Local filtered Hyperliquid retention already includes
  `node_fills_by_block`, `node_order_statuses_by_block`, and
  `node_raw_book_diffs_by_block`.
- `spec-026` now has implementation-tracking artifacts (`plan.md` and
  `tasks.md`), and the historical candidate-window JSON referenced by the
  checkpoint is present in the current worktree.

### Existing Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| `scripts/capture_provider_api.py` | Exists | Hyperliquid widget capture path patched and verified for local `ETH` capture |
| `scripts/coinglass_decode_standalone.js` | Exists | Used to decode verified CoinGlass Hyperliquid payloads |
| `data/validation/raw_provider_api/20260320T181726Z/manifest.json` | Exists | Verified `ETH`, `7 day`, `request_verified = true` |
| `data/validation/raw_provider_api/20260320T183040Z/manifest.json` | Exists | Verified `ETH`, `1 day`, `request_verified = true` |
| `data/validation/raw_provider_api/20260320T183129Z/manifest.json` | Exists | Verified `ETH`, `7 day`, same payload family as `1 day` |
| `data/validation/manifests/hyperliquid_coinglass_checkpoint_20260320.md` | Exists | Handoff/checkpoint document for resumed investigation |
| `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.md` | Exists | Historical inventory before harness fix |
| `data/validation/manifests/coinglass_hyperliquid_live_findings_20260320.md` | Exists | Live findings on symbol universe and payload semantics |
| `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.json` | Exists | Machine-readable historical capture inventory |
| `data/validation/manifests/coinglass_hyperliquid_decode_audit_20260320.json` | Exists | Machine-readable decode audit and payload field inventory |
| `data/validation/manifests/hyperliquid_filtered_candidate_windows_20260320.json` | Exists | Canonical saved baseline for current `1d` / `7d` node-side candidate windows |
| `scripts/ingest_hl_fills.py` | Exists | Converts filtered Hyperliquid fills into `hl_fills_l4` / `hl_liquidations_l4` |
| `/media/sam/4TB-NVMe/hyperliquid/filtered/*` | Exists locally | Canonical filtered node retention for fills, order statuses, raw book diffs, and related streams |

### Source Documents

- `specs/026-liqmap-model-calibration/spec.md`
- `specs/026-liqmap-model-calibration/sidecar-design.md`
- `data/validation/manifests/hyperliquid_coinglass_checkpoint_20260320.md`
- `data/validation/manifests/hyperliquid_filtered_candidate_windows_20260320.json`
- `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.md`
- `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.json`
- `data/validation/manifests/coinglass_hyperliquid_decode_audit_20260320.json`
- `data/validation/manifests/coinglass_hyperliquid_live_findings_20260320.md`
- `data/validation/raw_provider_api/20260320T170833Z/manifest.json`
- `data/validation/raw_provider_api/20260320T181726Z/manifest.json`
- `data/validation/raw_provider_api/20260320T183040Z/manifest.json`
- `data/validation/raw_provider_api/20260320T183129Z/manifest.json`
- `/media/sam/1TB/hyperliquid-node/README.md`
- `/media/sam/1TB/hyperliquid-node/ARCHITECTURE.md`
- `/media/sam/1TB/hyperliquid-node/docs/ARCHITECTURE-infra.md`

### Primary External References

- `https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint`
- `https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals`
- `https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations`
- `https://github.com/hyperliquid-dex/order_book_server`

### Required Environment / Data

- CoinGlass credentials available through the shared secret path used by
  `get_secret()` / `dotenvx`
- Local CoinGlass bundle/decode tooling for encrypted payload inspection
- Filtered Hyperliquid node retention from `/media/sam/4TB-NVMe/hyperliquid/`
- Access to `node_fills_by_block`, `node_order_statuses_by_block`,
  `node_raw_book_diffs_by_block`, plus the mark/oracle, funding, and
  collateral/equity-adjustment inputs required by the target high-fidelity
  reconstruction path
- Current retention assumption: the node currently exposes roughly `7d` of
  usable history, so immediate prototype work should stay within `1d` / `7d`

### Current Reference Artifacts

- `data/validation/raw_provider_api/20260320T181726Z/manifest.json`
- `data/validation/raw_provider_api/20260320T183040Z/manifest.json`
- `data/validation/raw_provider_api/20260320T183129Z/manifest.json`
- `data/validation/manifests/hyperliquid_coinglass_checkpoint_20260320.md`
- `data/validation/manifests/hyperliquid_filtered_candidate_windows_20260320.json`
- `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.md`
- `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.json`
- `data/validation/manifests/coinglass_hyperliquid_decode_audit_20260320.json`
- `data/validation/manifests/coinglass_hyperliquid_live_findings_20260320.md`
- `specs/026-liqmap-model-calibration/sidecar-design.md`

## Architecture

```
verified CoinGlass Hyperliquid captures
        +
decoded top-position payloads (`price` + `list`)
        +
local filtered Hyperliquid node streams
(`fills`, `order_statuses`, `raw_book_diffs`, `oracle/mark`, `funding`, `collateral`)
        ->
sidecar account-level reconstruction with cross-margin-safe retained state
        ->
bucketed ETH/BTC risk-surface artifacts
        ->
CoinGlass-vs-Rektslug comparison
        ->
go / no-go Hyperliquid parity decision
```

## Architecture Boundary

- Keep `hyperliquid-node` focused on canonical collection, filtering, and
  state anchoring.
- Implement BTC/ETH parity reconstruction, retained account-state modeling,
  and CoinGlass-facing comparison logic in a sidecar.
- Allow node-side changes only when they are generic infrastructure
  improvements, such as exporting or retaining state anchors/checkpoints that
  are broadly useful beyond this spec.
- Do not embed CoinGlass-specific heuristics or BTC/ETH-specific liquidation
  modeling into `hyperliquid-node`.

## What Already Works

- local Hyperliquid `ETH` CoinGlass capture is verified end-to-end
- CoinGlass Hyperliquid payload decoding works for saved artifacts
- timeframe behavior is bounded enough to say the payload is not exposing a
  distinct `1 day` vs `7 day` historical series
- local filtered node retention includes more than fills alone, which makes a
  stronger reconstruction path realistic
- periodic ABCI snapshots provide direct per-user clearinghouse state anchors,
  but only for the currently retained `2d` window
- the saved candidate-window baseline artifact is present locally and can be
  reused as the current `1d` / `7d` comparison baseline

## What Needs Work

1. inventory the actual schema and local availability of
   `node_order_statuses_by_block`, `node_raw_book_diffs_by_block`, mark/oracle,
   transfer/collateral-adjustment coverage, funding-rate inputs, and funding
   application timing
2. prove the exactness envelope: `snapshot-exact` over retained ABCI anchors vs
   replay between anchors, which is still unproven until collateral/funding
   gaps are bounded
3. formalize the sidecar retained account-state format needed to preserve exact
   cross-margin semantics for BTC/ETH-relevant accounts
4. generate a first local `ETH 7d` risk-surface artifact
5. compare shape, peak buckets, long/short balance, and stability against
   CoinGlass Hyperliquid
6. turn the saved candidate-window baseline into an explicit input of the next
   comparison/reporting steps
7. define the smallest possible generic node-side export/retention change, if
   any, that the sidecar actually needs

## Phases

1. Evidence freeze and reference index.
2. Node-stream inventory and reconstruction requirements.
3. Sidecar reconstruction design and exactness proof strategy.
4. ETH `1d` sensitivity check and retention-aware refinement.
5. BTC extension, comparison report, and parity decision.

## Acceptance Notes

- Treat CoinGlass Hyperliquid as a distinct product from CoinGlass
  per-exchange and aggregate liq maps.
- Do not treat the CoinGlass `1 day` / `7 day` UI as proof of historical
  timeframe unless a primary signal changes.
- Use local filtered Hyperliquid data as the canonical source; CoinGlass is a
  reference output, not ground truth.
- No accepted parity path may discard off-target exposure for accounts that are
  relevant to BTC/ETH liquidation under cross-margin.
- No accepted implementation path may move BTC/ETH-specific parity logic into
  `hyperliquid-node`; keep that logic in the sidecar.
- Local success is not just visual similarity. Record peak buckets,
  long/short balance, scale, and stability explicitly.

## Risks

- assuming fills alone are sufficient to reconstruct future liquidation risk
- missing transfer / deposit / withdrawal / collateral-adjustment events and
  silently drifting account equity between anchors
- treating funding-rate history as sufficient without proving the exact node-side
  funding application timing
- approximating away non-target positions for BTC/ETH-relevant accounts and
  silently breaking cross-margin liquidation semantics
- pushing parity-specific reconstruction logic into `hyperliquid-node` and
  coupling a general-purpose collector to an evolving research model
- assuming exact account-state reconstruction across `7d` before the replay
  path is validated against the `2d` ABCI anchors
- overfitting to CoinGlass visual smoothing instead of modeling real
  Hyperliquid risk
- assuming full source coverage for oracle/funding/collateral before verifying
  the concrete local streams and their semantics
