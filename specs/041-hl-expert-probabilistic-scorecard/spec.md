# Feature Specification: Hyperliquid Expert Probabilistic Scorecard

**Feature Branch**: `041-hl-expert-probabilistic-scorecard`
**Created**: 2026-04-30
**Status**: Draft
**Input**: Empirical evaluation framework for the four live Hyperliquid expert variants in `rektslug` (`v1`, `v3`, `v4`, `v5`)
**Dependencies**: spec-029 (expert snapshot producer contract), spec-038 (shadow mode), spec-039 (shadow pipeline runtime), spec-040 (continuous paper/testnet runtime)

## Context

`rektslug` already produces four internal Hyperliquid expert variants that matter
for current decisioning:

- `v1` - canonical full-universe baseline
- `v3` - top-position-like branch
- `v4` - position-first branch
- `v5` - risk-first branch

`v2` remains a `shadow/control` replay lane and is intentionally excluded from
the primary decision set for this spec.

Today the repo can already:

- produce timestamped expert artifacts under `data/validation/expert_snapshots/hyperliquid/`
- publish Redis signals from an expert artifact
- run shadow-mode correlation against live liquidation streams
- run continuous paper/testnet execution downstream in `nautilus_dev`

What is still missing is the right evaluation layer for expert quality itself.
The next step is **not** a weighted linear score and **not** a hand-tuned
parametric model. The next step is an empirical scorecard built from observed
event frequencies and realized post-touch outcomes.

The scorecard should answer questions such as:

- How often does each expert level get touched?
- After a touch, how often do real liquidation events appear nearby?
- After a touch, how often does price bounce, break, or continue?
- What do the empirical `MFE`, `MAE`, and time-to-event distributions look like?
- Which expert dominates in which regime, without forcing one global linear score?

This spec freezes that scorecard contract.

## Scope

### In Scope

- Define the event dataset for empirical expert evaluation
- Define non-parametric or near-non-parametric probability slices for `v1`, `v3`, `v4`, `v5`
- Define how to measure touch, liquidation confirmation, post-touch price path, and optional execution usefulness
- Define artifact outputs for machine-readable expert scorecards
- Define the ownership boundary between `rektslug` and `nautilus_dev`

### Out of Scope

- A single weighted global score with fixed linear coefficients
- Automatic live routing/ensemble weighting based on this spec alone
- Replacing shadow mode or continuous runtime gating
- Mainnet promotion policy
- Reclassifying `v2` as a production expert

## Ownership Boundary

### `rektslug` Responsibilities

- Produce and retain timestamped expert artifacts
- Build event-level observations tied to `expert_id`
- Measure empirical probabilities and realized outcome distributions
- Publish machine-readable expert scorecards and comparison artifacts

### `nautilus_dev` Responsibilities

- Optionally consume scorecard summaries as downstream decision support
- Continue to own execution runtime, operator controls, and final readiness gates

### Explicit Rule

`rektslug` owns **expert-quality measurement**.
`nautilus_dev` owns **execution-quality measurement**.

This spec must not drift into execution governance.

## Core Design Direction

### Explicit Non-Linear Rule

The scorecard MUST NOT start from a single formula of the form:

`score = a*x + b*y + c*z`

where the weights are manually chosen and globally fixed.

### Preferred Measurement Style

The scorecard MUST be based on empirical observations:

- event counts
- conditional frequencies
- quantiles
- bucketed distributions
- regime-conditioned slices

This can still include minimum-sample thresholds and confidence metadata, but
the primary contract is distributional and empirical, not parametric.

### No Forced Global Winner

The scorecard MUST allow results such as:

- `v1` dominates on touch frequency
- `v4` dominates on liquidation confirmation
- `v5` dominates on post-touch reward/risk

without collapsing those facts into one mandatory scalar rank.

## User Scenarios & Testing

### User Story 1 - Empirical Touch and Liquidation Reliability (Priority: P1)

As a researcher, I need to know how often each expert's predicted levels are
touched and how often those touches coincide with real liquidation activity.

**Why this priority**: Without this, expert comparison remains narrative and not
measured.

**Independent Test**: Build a scorecard from retained expert artifacts and
realized market/liquidation data, then verify that each expert has explicit
touch counts, touch probabilities, and liquidation confirmation counts.

**Acceptance Scenarios**:

1. **Given** a batch of expert artifacts and realized price/liquidation data,
   **When** the scorecard runs, **Then** each `expert_id` has an explicit
   `touch_count` and `touch_probability`.
2. **Given** touched levels for one expert, **When** liquidation events are
   checked in the declared confirmation window, **Then** the scorecard exposes
   `liquidation_match_count` and `P(liquidation | touch)`.
3. **Given** an expert has too few samples in one slice, **When** the scorecard
   emits output, **Then** the slice is flagged as low-sample rather than
   silently treated as reliable.

---

### User Story 2 - Post-Touch Price Path Quality (Priority: P1)

As a researcher, I need to know what happens after price touches a predicted
level, not only whether the touch occurred.

**Why this priority**: Some levels may be frequently touched but useless or
adversarial after touch.

**Independent Test**: For each expert, compute post-touch path summaries such as
empirical `MFE`, `MAE`, bounce rate, break rate, and time-to-touch.

**Acceptance Scenarios**:

1. **Given** a touched level, **When** the observation window closes,
   **Then** the scorecard records empirical `MFE` and `MAE`.
2. **Given** touched levels for one expert, **When** outcomes are aggregated,
   **Then** bounce and adverse-break frequencies are available per expert.
3. **Given** two experts with different behavior, **When** their distributions
   are compared, **Then** the scorecard preserves the difference instead of
   flattening both into the same scalar score.

---

### User Story 3 - Regime-Aware Comparison Without Manual Weights (Priority: P1)

As a researcher, I need to compare experts by regime so that one branch is not
declared globally better based only on one symbol or one volatility state.

**Why this priority**: Expert quality is conditional on context.

**Independent Test**: Compute scorecard slices by symbol, side, distance bucket,
confidence bucket, and volatility regime, then verify that each slice remains
machine-readable.

**Acceptance Scenarios**:

1. **Given** scorecard output for one symbol, **When** slices are inspected,
   **Then** the expert metrics are available by side and distance bucket.
2. **Given** two volatility regimes, **When** the same expert is compared across
   them, **Then** the output preserves regime-specific metrics instead of only a
   global average.
3. **Given** no data for one regime slice, **When** output is emitted,
   **Then** the slice is marked unavailable rather than backfilled with zeros.

## Edge Cases

- **Price never touches the predicted level**: The event remains a valid
  observation with `touched=false`; it must not be dropped.
- **Touch occurs but no liquidation stream event appears**: The observation
  remains valid and contributes to `P(liquidation | touch)` as a negative case.
- **Multiple touches of the same level inside one observation window**: The
  scorecard MUST declare whether it measures first-touch or all-touch semantics.
  MVP uses first-touch semantics unless a later phase explicitly adds repeated-touch modeling.
- **Liquidation events appear before price touch**: They do not count toward
  `P(liquidation | touch)` for that observation.
- **One expert artifact missing for a timestamp**: That timestamp remains part of
  coverage accounting and is marked unavailable for the missing expert.
- **Execution runtime is unavailable for one observation**: Signal-quality
  metrics still compute; execution-quality metrics for that row are null rather
  than fabricated.
- **Too few observations**: The slice must be emitted with sample counts and a
  low-confidence or low-sample marker.

## Requirements

### Functional Requirements

- **FR-001**: The scorecard MUST evaluate `v1`, `v3`, `v4`, and `v5` as the four primary Hyperliquid experts.
- **FR-002**: `v2` MAY be included as an optional control lane, but it MUST NOT be required for the primary four-expert scorecard.
- **FR-003**: Every scorecard observation row MUST retain `expert_id`, `symbol`, `snapshot_ts`, `level_price`, `side`, and `confidence`.
- **FR-004**: The scorecard MUST preserve observations where no touch occurs. Non-events are data.
- **FR-005**: The scorecard MUST compute at least:
  - `P(touch | signal)`
  - `P(liquidation_confirmation | touch)`
  - empirical `MFE`
  - empirical `MAE`
  - `time_to_touch`
- **FR-006**: The scorecard MUST expose sample counts for every reported probability or distribution slice.
- **FR-007**: The scorecard MUST support slicing by at least:
  - `symbol`
  - `side`
  - distance-to-price bucket
  - confidence bucket
- **FR-008**: The scorecard SHOULD support a volatility-regime slice when regime labels are available.
- **FR-009**: The scorecard MUST distinguish signal-quality metrics from execution-quality metrics.
- **FR-010**: Execution-quality metrics, when present, MUST remain clearly optional and downstream-derived.
- **FR-011**: The scorecard MUST NOT emit a mandatory single scalar "best expert" score in MVP.
- **FR-012**: The scorecard MUST emit machine-readable artifacts that let downstream reviewers compare experts without importing internal script logic.
- **FR-013**: The scorecard MUST record coverage and missing-data metadata so that absent expert artifacts or absent market windows are explicit.
- **FR-014**: The scorecard MUST support historical backfill from retained expert artifacts.
- **FR-015**: The scorecard MUST support incremental append for new live/shadow observations.
- **FR-016**: The scorecard MUST define explicit observation windows for:
  - touch detection
  - liquidation confirmation
  - post-touch path evaluation
- **FR-017**: The scorecard MUST declare whether touch detection uses exact level touch, tolerance bands, or bucket overlap semantics. MVP target is explicit tolerance-band semantics.
- **FR-018**: The scorecard MUST keep retained evidence and live runtime state separate; scorecard history is not a substitute for current runtime health.
- **FR-019**: The scorecard MUST provide comparison outputs that allow dominance analysis across experts per slice.
- **FR-020**: If one slice is below minimum sample thresholds, the output MUST mark it as insufficient rather than defaulting to zeros or stable-looking probabilities.

### Non-Functional Requirements

- **NFR-001**: The scorecard pipeline SHOULD be reproducible from retained artifacts and declared market/liquidation sources.
- **NFR-002**: The scorecard MUST remain machine-readable first; markdown summaries are secondary.
- **NFR-003**: The scorecard SHOULD be append-safe and idempotent for reruns on the same observation window.
- **NFR-004**: MVP should avoid expensive parametric fitting or global optimization loops.

## Key Entities

- **ExpertSignalObservation**: One predicted level from one expert at one timestamp, with metadata needed for ex-post evaluation.
- **TouchOutcome**: Whether and when price touched the level inside the configured touch window.
- **LiquidationConfirmationOutcome**: Whether and when real liquidation activity occurred near the level after touch.
- **PathOutcome**: Post-touch path features such as `MFE`, `MAE`, bounce classification, and break classification.
- **ExecutionOutcome**: Optional downstream execution result fields such as accepted, filled, closed, and realized paper PnL.
- **ExpertScorecardSlice**: Aggregated empirical metrics for one expert under one slice definition.
- **ExpertScorecardBundle**: Machine-readable artifact containing slices, counts, coverage metadata, and comparison outputs.

## Initial Observation Contract

Each `ExpertSignalObservation` MUST contain at least:

- `observation_id`
- `expert_id`
- `symbol`
- `snapshot_ts`
- `level_price`
- `side`
- `confidence`
- `reference_price`
- `distance_bps`
- `touched`
- `touch_ts`
- `liquidation_confirmed`
- `liquidation_confirm_ts`
- `mfe_bps`
- `mae_bps`
- `time_to_touch_secs`
- `time_to_liquidation_confirm_secs`

Optional downstream execution fields:

- `signal_accepted`
- `order_submitted`
- `position_opened`
- `position_closed`
- `feedback_persisted`
- `paper_pnl`

## Initial Scorecard Output Contract

Each `ExpertScorecardSlice` MUST contain at least:

- `expert_id`
- `slice_id`
- `slice_dimensions`
- `sample_count`
- `touch_count`
- `touch_probability`
- `liquidation_match_count`
- `liquidation_match_probability_given_touch`
- `mfe_quantiles`
- `mae_quantiles`
- `time_to_touch_quantiles`
- `low_sample_flag`

The bundle SHOULD also include:

- expert-vs-expert dominance rows
- coverage gaps
- retained input range
- artifact/source provenance

## Success Criteria

- The repo can produce one machine-readable scorecard bundle for `v1`, `v3`, `v4`, `v5` over BTC and ETH.
- Reviewers can answer "which expert is better under which condition?" without relying on one global linear score.
- Scorecard outputs distinguish:
  - no touch
  - touch without liquidation confirmation
  - touch with liquidation confirmation
  - favorable vs adverse post-touch path
- The same retained artifact set can be rerun reproducibly.

