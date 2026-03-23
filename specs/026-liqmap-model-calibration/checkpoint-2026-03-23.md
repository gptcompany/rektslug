# Checkpoint 2026-03-23: Spec-026 Handoff

## Scope State

`spec-026` is functionally closed for the original parity decision, but the consumer-side reserved-margin investigation is still active.

Current state:
- sidecar builder, comparison flow, and parity memo are complete
- consumer-side ABCI streaming decode is implemented
- bounded order-state reconstruction from retained feeds is implemented
- bounded reserved-margin proxy report is implemented and now runs successfully on a real retained sample
- outlier drill-down is implemented for targeted follow-up analysis

## Latest Reviewable Commits

Recommended review order:
1. `75e46c9` `Fix reserved-margin report lifecycle`
2. `c5cff7d` `Add reserved-margin outlier drilldown`

Earlier prerequisite commits on the same line of work:
1. `905da01` `Add bounded Hyperliquid order-state reconstruction`
2. `dbbc85d` `Add bounded reserved-margin proxy tooling`
3. `21c3bbb` `Stream ABCI target-user decoding`

## Confirmed Findings

### 1. Off-target order state is materially relevant

Real sample artifacts:
- [`hl_order_state_reconstruction_eth_sample.json`](/media/sam/1TB/rektslug/data/validation/hl_order_state_reconstruction_eth_sample.json)
- [`hl_reserved_margin_proxy_eth_sample.json`](/media/sam/1TB/rektslug/data/validation/hl_reserved_margin_proxy_eth_sample.json)
- [`hl_reserved_margin_outliers_eth_sample.json`](/media/sam/1TB/rektslug/data/validation/hl_reserved_margin_outliers_eth_sample.json)

From the retained pair `20260321/2.zst` plus anchor `20260321/931220000.rmp`:
- `370` active anchor-relevant users
- `205.66M` lower-bound exposure-increasing notional
- `117.39M` off-target lower-bound
- `88.27M` target-coin (`ETH`) lower-bound
- `181/370` users with positive off-target bounds

Conclusion:
- reserved-margin parity cannot be scoped to target-coin orders only
- off-target BTC/HYPE resting orders are first-class parity inputs for ETH-relevant users

### 2. `snapshot M` is not an open-order reserve proxy

Artifact:
- [`hl_open_order_margin_gap_eth_7d.json`](/media/sam/1TB/rektslug/data/validation/hl_open_order_margin_gap_eth_7d.json)

Confirmed earlier and still valid:
- aggregate `M` vs solver MMR gap is dominated by large negative whale cases
- `M - MMR` cannot be used directly as current reserved margin

### 3. High `abs(M-MMR)` users are not uniformly "high opening reserve" users

Outlier drill-down from [`hl_reserved_margin_outliers_eth_sample.json`](/media/sam/1TB/rektslug/data/validation/hl_reserved_margin_outliers_eth_sample.json):
- some top gap users have mostly `reducing_or_closing` active orders
- some have zero opening lower bound on active orders
- some are clear `opening_flat` or `opening_same_side` cases

Conclusion:
- residual gap cannot be attributed blindly to currently active resting orders alone
- likely missing semantics still include order-reserve formula details, carry-in state outside the retained feed window, and/or other account-state semantics

## Fixes Landed During This Session

### Lifecycle / memory fix

In [`sidecar.py`](/media/sam/1TB/rektslug/src/liquidationheatmap/hyperliquid/sidecar.py), `reconstruct_resting_orders_from_blocks()` now drops stale `metadata_by_key` entries when an order is terminal or removed.

Why it mattered:
- real reserved-margin runs were regrowing memory because metadata accumulated for dead orders
- after the fix, the real sample run stayed around tens of MB RSS instead of multi-GB growth

### JSON serialization fix

In [`analyze_hl_reserved_margin_proxy.py`](/media/sam/1TB/rektslug/scripts/analyze_hl_reserved_margin_proxy.py), report writing now converts frozen mappings to JSON-native structures.

Why it mattered:
- the real run previously reached the end and failed only at `json.dump()` because `mappingproxy` is not serializable

## Current Spec Docs Updated

Relevant docs:
- [`tasks.md`](/media/sam/1TB/rektslug/specs/026-liqmap-model-calibration/tasks.md)
- [`sidecar-design.md`](/media/sam/1TB/rektslug/specs/026-liqmap-model-calibration/sidecar-design.md)
- [`parity-decision.md`](/media/sam/1TB/rektslug/specs/026-liqmap-model-calibration/parity-decision.md)

Current documented position:
- consumer owns retention/checkpointing beyond producer rolling windows
- bounded reserved-margin proxy exists and has real retained-sample evidence
- off-target order state is materially necessary
- outlier drill-down shows active-order reserve is not the whole remaining explanation

## Exact Open Problem

Still unresolved:
- derive a tighter consumer-side reserved-margin semantics from the order-state we can observe

This is now a narrower problem than before.
It is no longer blocked by:
- full ABCI materialization
- retained-feed memory blow-up
- report serialization

It is still blocked by missing semantic proof, not by tooling.

## Recommended Next Session Plan

### Priority 1: derive a candidate reserved-margin formula

Goal:
- move from bounded notional to a candidate margin-reserve calculation that can be falsified against real outliers

Concrete steps:
1. use [`hl_reserved_margin_outliers_eth_sample.json`](/media/sam/1TB/rektslug/data/validation/hl_reserved_margin_outliers_eth_sample.json) as the starting dataset
2. cluster cases by order classification mix:
   - mostly `opening_same_side`
   - mixed `opening_same_side` + `partially_opening_opposite`
   - mostly `reducing_or_closing`
   - `opening_flat`
3. implement a new diagnostic script that computes candidate reserve formulas per user, for example:
   - MMR on opening-side notional only
   - IMR/MMR-like tiered reserve on opening-side notional
   - max(side reserves) vs sum(side reserves)
   - target-only reserve vs all-coins reserve
4. compare candidate reserve outputs against `margin_gap_total` on the same selected users
5. document which candidate explains which cluster and which clusters remain unexplained

### Priority 2: bound carry-in effects

Goal:
- measure how much the lack of pre-window carry-in orders can distort the current reserved-order reconstruction

Concrete steps:
1. extend the reconstruction/analyzer path from single retained file to multi-file retained window
2. keep the same bounded semantics, but include more prehistory when locally available
3. compare the same top users with larger replay windows to see whether opening/reducing classification materially changes

### Priority 3: prepare a consumer checkpoint design

Goal:
- be ready to make reserved-margin analysis and historical 7d work stable without touching `hyperliquid-node`

Concrete steps:
1. define a compact consumer checkpoint payload for:
   - target-relevant users
   - off-target positions
   - active/resting orders
   - minimal metadata needed for reserve recomputation
2. record frequency and storage estimate
3. keep this entirely consumer-owned

## Recommended First Commands For Resume

From repo root:

```bash
git show --stat 75e46c9
git show --stat c5cff7d
jq '{metadata, summary}' data/validation/hl_reserved_margin_proxy_eth_sample.json
jq '{metadata, users: [.users[] | {user, rankings, class_counts: (.orders | group_by(.classification) | map({classification: .[0].classification, count: length}))}]}' data/validation/hl_reserved_margin_outliers_eth_sample.json
```

If continuing with the next diagnostic:

```bash
uv run python scripts/analyze_hl_reserved_margin_outliers.py --top-n 5
```

## Validation State At Handoff

Last verified locally:
- `.venv/bin/pytest tests/test_hyperliquid_sidecar.py -q` -> `15 passed`
- `uv run python -m py_compile` on touched files -> ok
- real report generation completed successfully for:
  - `hl_reserved_margin_proxy_eth_sample.json`
  - `hl_reserved_margin_outliers_eth_sample.json`

## Resume Instruction

In the next session, do not restart from broad parity investigation.
Resume from:
- reserved-margin semantics derivation
- using the existing sample artifacts and the two latest commits as the checkpoint baseline
