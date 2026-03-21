# Phase 4 Sidecar Design: Exact BTC/ETH Cross-Margin Parity

## Goal

Build a sidecar reconstruction engine that can produce BTC/ETH liquidation-surface
artifacts while preserving exact account-level cross-margin semantics for any
relevant account, including accounts that also carry off-target asset exposure.

## Decision

- Keep `hyperliquid-node` as the canonical collection, filtering, and state-anchor layer.
- Implement replay, retained account state, parity comparison, and risk-surface generation in a sidecar.
- Allow node changes only when they are generic infrastructure improvements, such as longer retention/export for state anchors or a generic compact checkpoint exporter.
- Do not embed BTC/ETH-specific or CoinGlass-specific modeling logic into `hyperliquid-node`.

## Exactness Envelope

| Quantity | Status | Primary source | Notes |
|----------|--------|----------------|-------|
| Account raw state at snapshot time | `snapshot-exact` | `periodic_abci_states` | Applies only at retained ABCI timestamps |
| Multi-asset positions, margin, leverage, funding fields at snapshot time | `snapshot-exact` | `periodic_abci_states` | Relevant accounts must retain all assets, not just BTC/ETH |
| BTC/ETH fills and liquidation events inside filtered retention | `replay-exact candidate` | `filtered/node_fills_by_block` | Event ordering is block-native, but exactness also requires fills/liquidations for any *other* asset held by the relevant account to preserve cross-margin equity |
| BTC/ETH order lifecycle and open-order deltas | `replay-exact candidate` | `filtered/node_order_statuses_by_block`, `filtered/node_raw_book_diffs_by_block` | Needed for open-order state; also requires non-BTC/ETH order activity for relevant accounts to preserve reserved-margin exactness |
| Oracle / mark price updates | `replay-exact candidate` | `filtered/hip3_oracle_updates_by_block` | For Hyperliquid perps this must use the perp deployer mark stream (`hyna:BTC`, `hyna:ETH`), not `cash:BTC` |
| Collateral adjustments / deposits / withdrawals | `not reconstructable between snapshots` | no confirmed local stream yet | Missing this stream blocks replay exactness because intra-window deposits/withdrawals change the liquidation threshold |
| Funding rates | `available, application timing unproven` | `ccxt-data-pipeline/data/catalog/funding_rate/*HYPERLIQUID` | Rate history is local, but the exact node-side application schedule into account state is not yet confirmed; path-drift risk exists between anchors |
| Exact replay across the currently retained ~2d anchor window | `not yet proven` | ABCI + filtered + funding | Re-anchor proof is blocked until collateral-adjustment coverage, funding application timing, and off-target activity are bounded |
| Exact replay across `7d` | `not yet proven` | needs anchor at or before window start | Current local ABCI retention is only ~2d, so exact `7d` parity cannot be claimed yet |
| CoinGlass-like visual smoothing / palette / chart rendering | `approximate` | sidecar only | Presentation layer, never source truth |
| CoinGlass parity judgment | `derived` | comparison report | Depends on replay proof plus modeling choices |

## Relevant Account Rule

An account becomes BTC/ETH-relevant for a given analysis window if any of the following is true:

- it holds a BTC or ETH position in an ABCI anchor inside or immediately before the window
- it appears in BTC or ETH fills/liquidations during the window
- it appears in BTC or ETH order-status or raw-book-diff events during the window

Relevance is sticky for the whole analysis window. If primary BTC/ETH relevance is true,
the sidecar must retain the full account state, including off-target assets and any
margin-affecting open-order state needed for cross-margin exactness.

## Retained Account State V0

The retained state should use two layers so schema knowledge can improve without
throwing away exactness.

### 1. Raw anchor layer

Lossless per-account state captured from ABCI anchors for each relevant account:

- `snapshot_ref`: source path, block identifier, snapshot timestamp, universe/version hash
- `user_state_raw`: full decoded `user_to_state` entry for that account
- `open_order_tracker_raw`: any matching open-order / reserved-margin subtree from `user_states.open_order_tracker`; presence is confirmed in the ABCI snapshots, but structured extraction still needs explicit inventory
- `users_with_positions_flag`: whether the account is active in the anchor
- `raw_hash`: stable digest of the retained raw subtree for later drift checks

### 2. Normalized layer

Sidecar-owned parsed view derived from the raw layer and replay events:

- `address`
- `balance_state`: parsed balance/collateral fields derived from `S`
- `positions_by_asset_idx`: all assets for the account, each retaining:
  - `raw_position`
  - parsed fields when decoder confidence is sufficient: size, entry/avg price, margin, leverage mode, funding accumulator, side/sign
- `orders_by_oid`: all tracked open orders affecting margin/liquidation semantics
- `asset_meta_version`: mapping back to the anchor universe/asset index set
- `last_mark_state`: most recent oracle/mark values used by replay

### 3. Event journal layer

Append-only events applied after the anchor:

- fills / liquidations
- order status transitions
- raw book diffs
- oracle updates
- funding updates

### 4. Derived layer

Values computed from normalized state and used by the builder:

- equity time series
- maintenance margin and liquidation thresholds
- liquidation-price candidates / bucket contributions for BTC and ETH
- validation fingerprints against later anchors

## Why raw + normalized

The raw layer protects exactness while the decoder is still maturing. The normalized
layer can evolve as field meanings are proven, without losing the original retained
account subtree needed to re-check or re-parse state later.

## Replay Strategy

1. Start from the latest retained anchor at or before the analysis-window start.
2. Build the relevant-account set from that anchor plus a forward scan of BTC/ETH event streams.
3. For every relevant account, keep all assets and all margin-affecting open-order state.
4. Replay fills, order-status changes, raw-book diffs, oracle updates, and funding updates in block/time order.
5. At each later ABCI anchor, re-materialize the same relevant accounts and compare the sidecar state to the raw anchor state.
6. Only label the replay `exact` for a window if the re-anchor diffs close cleanly.

## Exactness Proof Rules

A replay window can be called exact only if all of the following hold:

- there is an anchor at or before the window start
- relevant accounts are selected without dropping off-target exposures (positions OR orders)
- all collateral adjustments and funding applications for those accounts are captured; matching a later anchor only validates the endpoint, not the path between anchors (intra-window drift risk)
- sidecar state at later anchors matches the raw anchor state for these **Target Invariants**:
  - USDC balance / collateral state
  - position size for all assets retained on the account
  - per-position funding accumulator / margin-mode state
  - open-order / reserved-margin state
- any remaining mismatches are explained as parser/decoder gaps and driven to zero before claiming parity

Next-anchor zero-drift is a necessary but not sufficient condition for 'replay-exact' status. Without path-exactness (observed transfers and funding applications), the replay status remains bounded to the anchors.

Without an anchor covering the window start, exact parity is not claimable. In the
current local setup this means:

- snapshot exactness is hard-confirmed at retained ABCI anchors over the current ~2d window
- replay exactness between those anchors is still unproven until path-drift risks (transfers, funding, off-target activity) are bounded
- exact `7d` parity needs either longer-lived anchors or a generic compact checkpoint retained for at least `7d`

## First Builder V0 Parameters

For the first ETH/BTC builder, use the existing repository bin-resolution path instead of inventing a new grid.

- `price_bin_size`: resolve with the same profile-driven logic already used by the API/cache path; today that means the `rektslug-ank` profile with fallback `ETH=10.0` and `BTC=100.0` when profile resolution fails
- `bucket assignment`: solve the target-asset liquidation price for the account under frozen non-target marks, then round that liquidation price onto the resolved bin grid
- `accumulation metric`: sum current-mark target-asset notional, `abs(target_size) * current_mark`, into the solved liquidation bucket
- `side split`: derive directly from the sign of the target-asset net position; long exposure contributes to long-liquidation buckets and short exposure contributes to short-liquidation buckets
- `cross-margin treatment`: off-target assets do not get aggregated into bucket weight directly, but they must remain in the retained account state because they change equity, maintenance margin, and the solved liquidation threshold

This is a builder choice, not a source-of-truth claim about CoinGlass internals. The exactness claim applies to the retained state and the solved liquidation threshold under this one-dimensional target-asset shock model.

## Minimal Allowed `hyperliquid-node` Changes

Allowed if the sidecar needs them:

- longer retention or export of generic state anchors
- a generic compact checkpoint exporter that is not BTC/ETH-specific
- generic metadata needed to decode anchors consistently across versions

Not allowed inside the node:

- BTC/ETH-only filtering for parity logic
- CoinGlass-specific heuristics
- liquidation-surface modeling logic

## Immediate Implementation Consequences

- `T017` must remain open until transfer/collateral coverage and funding-application timing are explicitly bounded.
- `T018` is satisfied by the exactness envelope above.
- `T020` is satisfied by `Retained Account State V0` and the relevant-account rule.
- `T022` is satisfied by the explicit anchor/retention constraint for `2d` vs `7d`.
- `T023` is satisfied by this note and the node/sidecar boundary it defines.
- `T021` is satisfied by `First Builder V0 Parameters`, which reuses the repo bin-size resolver and fixes the first accumulation/side-split choice.
