# Phase 4 Sidecar Design: Exact BTC/ETH Cross-Margin Parity

## Goal

Build a sidecar reconstruction engine that can produce BTC/ETH liquidation-surface
artifacts while preserving exact account-level cross-margin semantics for any
Hyperliquid account identified as "relevant" during the analysis window.

## Exactness Envelope

| Quantity | Status | Primary source | Notes |
|----------|--------|----------------|-------|
| ABCI snapshot anchoring (balances, positions) | `snapshot-exact` | `periodic_abci_states/*.rmp` | Confirmed: `user_to_state` and `p.p` are lists of pairs, not maps |
| Position Cost (`e`) and Size (`s`) | `exact` | `p.p[idx]` | Confirmed: `e` is Total Cost (1e6), `s` is Size (10^szDecimals) |
| Oracle / mark price updates | `exact` | `cls[0].oracle.pxs` | Scaled as `px * 10^(7 - szDecimals)`; used for cross-margin PnL |
| Maintenance Margin Rates (MMR) | `exact` | `cls[0].meta.marginTableIdToMarginTable` | Extracted per-asset tiers; MMR = 1 / (2 * max_leverage) |
| BTC/ETH fills and liquidation events | `replay-exact candidate` | `filtered/node_fills_by_block` | Needed for path-exactness between anchors |
| Collateral adjustments / funding | `funding exact, transfers missing` | ABCI + CCXT | Funding integrated via `f.a`; transfers still block path-exactness |
| Presentation layer / bucket smoothing / palette / chart rendering | `approximate` | sidecar only | Presentation layer, never source truth |
| CoinGlass parity judgment | `derived` | comparison report | Depends on replay proof plus modeling choices |

## Relevant Account Rule

An account is "BTC/ETH-relevant" if it satisfies any of these in the analysis window:
- it holds a non-zero BTC or ETH position at any ABCI anchor
- it generates a fill or liquidation event on BTC or ETH
- it contributes to BTC/ETH liquidation semantics through cross-margin because the same account also carries off-target exposure while being BTC/ETH-relevant

Once an account is marked relevant, the sidecar must retain the **full account state**, including off-target assets and any margin-affecting open-order state needed for cross-margin exactness.

## Cross-Margin Solver (V1)

The sidecar implements an exact solver for the target asset liquidation price ($P_{target}$):

$$AccountValue < MaintenanceMarginRequirement$$

Where:
- $AccountValue = Balance + \sum (Size_i \times (Mark_i - Entry_i)) - \sum (Funding\_Correction_i)$
- $MMR = \sum (Notional_i \times MMR\_Rate_i - Maintenance\_Deduction_i)$

By freezing non-target marks, we solve for $P_{target}$ where $AccountValue = MMR$.
The implementation correctly handles the `Maintenance Deduction` and `MMR Tiers` extracted from the node metadata.

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

- bin size: `profile-resolved` (reusing repo bin-size resolver)
- accumulation metric: sum current-mark target-asset notional (abs size * mark) into the solved liquidation bucket
- side split: determined by target-position sign (positive = long, negative = short)
- unliquidatable accounts: if solved `liq_price <= 0`, the account's notional is excluded from the visible surface

## Constraints

- `T022` is satisfied by the logic distinguishing `1d` vs `7d` for `2d` vs `7d`.
- `T023` is satisfied by this note and the node/sidecar boundary it defines.
- `T021` is satisfied by `First Builder V0 Parameters`, which reuses the repo bin-size resolver and fixes the first accumulation/side-split choice.
