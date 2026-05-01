# Feature Specification: Adaptive Observation Layer for Expert Scorecard

**Feature Branch**: `042-adaptive-observation-layer`
**Created**: 2026-05-01
**Status**: Draft
**Input**: Replace all hardcoded parameters in spec-041 scorecard with data-derived functions
**Dependencies**: spec-041 (expert probabilistic scorecard)
**Pillar Alignment**: Probabilistico, Non Lineare, Non Parametrico, Scalare

## Context

spec-041 delivered a working empirical scorecard for Hyperliquid experts `v1`, `v3`,
`v4`, `v5`. The contracts, slicing, dominance rows, backfill, and reproducibility are
solid. However, the observation layer still relies on five hardcoded parameters:

| Parameter | Current Value | Pillar Violation |
|-----------|--------------|------------------|
| Touch tolerance | 5 bps fixed | Non Parametrico |
| Touch window | 4 hours fixed | Non Parametrico, Scalare |
| Post-touch window | 1 hour fixed | Non Parametrico, Scalare |
| Liquidation confirm window | 15 min fixed | Non Parametrico |
| Distance/confidence buckets | Manual ranges | Non Parametrico, Non Lineare |

These are reasonable MVP defaults, but they are a manual cage. A 5 bps tolerance
treats BTC at 100k and a low-cap altcoin identically. A 1-hour post-touch window
treats a volatile US-open session the same as overnight drift. Fixed bucket
boundaries impose linear partitions on non-linear distributions.

This spec replaces every hardcoded constant with a function of the observed data.

## Foundational Rule

**If a threshold, window, or boundary can be computed from the data, it MUST NOT
be a constant in the code.**

Every parameter becomes a function of the empirical distribution. The only
acceptable "constants" are mathematical identities (quantile indices, bootstrap
sample counts) that define the computation method, not the output value.

## Scope

### In Scope

- Replace touch tolerance with a volatility-derived adaptive band
- Replace time-based observation windows with volume-clock primitives
- Replace hardcoded bucket boundaries with empirical quantile partitions
- Replace winner-takes-all dominance with bootstrap confidence intervals
- Replace manual regime labels with data-inferred regime assignment
- Retain backward compatibility with spec-041 contract shapes

### Out of Scope

- Predictive models, ML classifiers, or parametric fitting
- Changes to nautilus_dev execution runtime
- Mainnet promotion policy
- Replacing the spec-041 contract models themselves (extend, not replace)
- Global weighted expert ranking

## Ownership Boundary

Identical to spec-041: `rektslug` owns expert-quality measurement. `nautilus_dev`
owns execution-quality measurement. This spec does not drift into execution
governance.

## User Scenarios & Testing

### User Story 1 - Adaptive Touch Detection (Priority: P1)

As a researcher, I need touch detection to adapt to the current volatility of
each symbol so that a touch on BTC during low-vol overnight is not measured with
the same band as BTC during a liquidation cascade.

**Why this priority**: Touch detection is the entry gate for every downstream
metric. If the tolerance band is wrong, every probability and quantile downstream
is distorted.

**Independent Test**: Run the scorecard on the same expert artifact twice — once
during a low-volatility window, once during a high-volatility window — and verify
that the tolerance band widens in the high-vol case and narrows in the low-vol case.

**Acceptance Scenarios**:

1. **Given** a symbol with low recent realized volatility, **When** the scorecard
   computes the touch band, **Then** the band is narrower than the spec-041 fixed
   5 bps default.
2. **Given** a symbol with high recent realized volatility, **When** the scorecard
   computes the touch band, **Then** the band is wider than the spec-041 fixed
   5 bps default.
3. **Given** two symbols with different volatility profiles at the same timestamp,
   **When** their touch bands are compared, **Then** they differ.

---

### User Story 2 - Volume-Clock Observation Windows (Priority: P1)

As a researcher, I need observation windows measured in traded volume, not wall-clock
time, so that 1 hour of overnight drift is not treated as equivalent to 1 hour
during US-open when 10x more volume trades.

**Why this priority**: Time-based windows violate both Non Parametrico (fixed
constant) and Scalare (different meaning across regimes). Volume-clock is the
natural unit for market-microstructure observation.

**Independent Test**: Run the scorecard on the same touch event with two different
volume profiles (low-volume overnight vs. high-volume session) and verify that the
observation window closes at different wall-clock times but at the same
volume-threshold.

**Acceptance Scenarios**:

1. **Given** a touched level with high post-touch volume, **When** the observation
   window evaluates, **Then** the window closes sooner in wall-clock time than for
   a low-volume touch.
2. **Given** a touched level, **When** the post-touch path is evaluated, **Then**
   MFE and MAE are computed up to the volume-threshold, not a fixed time horizon.
3. **Given** insufficient post-touch volume data, **When** the window cannot close
   on volume alone, **Then** the observation is marked as incomplete rather than
   truncated at an arbitrary time.

---

### User Story 3 - Data-Derived Bucketing (Priority: P1)

As a researcher, I need distance and confidence buckets derived from the empirical
distribution of observed values, not from manually chosen ranges, so that the
scorecard partitions reflect the actual data shape.

**Why this priority**: Fixed linear buckets (0-25, 25-50, ...) impose an arbitrary
grid that may split dense clusters or merge sparse tails. Quantile-based buckets
guarantee equal observation counts per bucket, maximizing statistical power per
slice.

**Independent Test**: Run the scorecard on a dataset with skewed distance
distribution and verify that the bucket boundaries differ from the spec-041
hardcoded values and that each bucket contains approximately equal observation
counts.

**Acceptance Scenarios**:

1. **Given** a set of observations, **When** distance buckets are computed,
   **Then** boundaries are at empirical quantiles of the `distance_bps` distribution.
2. **Given** a set of observations, **When** confidence buckets are computed,
   **Then** boundaries are at empirical quantiles of the `confidence` distribution.
3. **Given** different datasets with different distributions, **When** buckets are
   computed for each, **Then** the bucket boundaries differ between datasets.
4. **Given** fewer than a minimum number of observations, **When** bucketing is
   attempted, **Then** the system falls back to a single "all" bucket rather than
   producing empty quantile bins.

---

### User Story 4 - Probabilistic Dominance (Priority: P2)

As a researcher, I need expert-vs-expert comparisons to express uncertainty via
bootstrap confidence intervals, not just point-estimate winners, so that I know
whether a dominance claim is robust or noise.

**Why this priority**: Point-estimate dominance (e.g., "v4 has higher touch_probability
than v1") can be driven by a single observation. Bootstrap CI makes the comparison
honest.

**Independent Test**: Run the scorecard with two experts that have similar
performance on a slice and verify that the dominance output reports the comparison
as inconclusive rather than declaring a winner.

**Acceptance Scenarios**:

1. **Given** two experts with clearly different performance on a slice, **When**
   dominance is computed, **Then** the output includes a probability estimate
   (e.g., `P(v4 > v1) = 0.92`) and marks it as significant.
2. **Given** two experts with similar performance on a slice, **When** dominance
   is computed, **Then** the output marks the comparison as inconclusive.
3. **Given** a slice with very few observations, **When** dominance is computed,
   **Then** the confidence interval is wide and the comparison is marked
   inconclusive rather than picking a winner from noise.

---

### User Story 5 - Data-Inferred Regime (Priority: P2)

As a researcher, I need regimes assigned automatically from observed market features
(realized volatility, liquidation intensity, funding rate stress) rather than
manually supplied labels, so that regime-conditioned slices update as the market
evolves.

**Why this priority**: Manual regime labels are a parametric cage. Data-inferred
regimes complete the Non Parametrico alignment.

**Independent Test**: Run the scorecard on a dataset spanning a known vol-regime
transition and verify that the system assigns different regime labels to
observations before and after the transition without manual input.

**Acceptance Scenarios**:

1. **Given** a set of observations spanning different market conditions, **When**
   regimes are inferred, **Then** at least two distinct regime labels are assigned.
2. **Given** observations from a stable low-volatility period, **When** regime is
   inferred, **Then** all observations in that period share the same regime label.
3. **Given** no market feature data is available, **When** regime inference runs,
   **Then** all observations are assigned a single "unknown" regime rather than
   failing.

---

### Edge Cases

- **Zero volume after touch**: The volume-clock window cannot close. The observation
  must be marked incomplete with a reason, not silently dropped or force-closed at
  an arbitrary time.
- **Single observation in a quantile bucket**: The bucket exists but is flagged as
  low-sample. Probabilities are still computed but marked unreliable.
- **All experts identical on a slice**: Bootstrap dominance correctly reports all
  pairwise comparisons as inconclusive.
- **Volatility data unavailable for adaptive band**: Fall back to the empirical
  spread of the price path itself (min-max range / mean) as a volatility proxy.
  Never fall back to the fixed 5 bps constant.
- **Dataset too small for quantile bucketing**: Use a single "all" bucket. Never
  fabricate empty quantile bins.
- **Volume data missing from price path**: Mark observations as incomplete for
  volume-clock metrics. Time-based metrics may still be emitted as secondary
  metadata if the price path has timestamps.

## Requirements

### Functional Requirements

- **FR-001**: The touch tolerance band MUST be computed as a function of recent
  realized volatility (or a volatility proxy) for the observation's symbol and
  timestamp. No fixed bps constant.
- **FR-002**: The primary observation window (post-touch path, MFE/MAE evaluation)
  MUST close on a volume-based criterion, not a fixed time horizon.
- **FR-003**: Time-based windows MAY be retained as secondary metadata for debugging
  and comparison, but MUST NOT be the primary evaluation boundary.
- **FR-004**: Distance bucket boundaries MUST be derived from empirical quantiles of
  the observed `distance_bps` distribution.
- **FR-005**: Confidence bucket boundaries MUST be derived from empirical quantiles
  of the observed `confidence` distribution.
- **FR-006**: The number of quantile buckets SHOULD be adaptive: more buckets when
  enough data exists, fewer (down to one) when data is sparse.
- **FR-007**: Expert-vs-expert dominance MUST use bootstrap resampling to produce
  pairwise probability estimates with uncertainty bounds.
- **FR-008**: Dominance output MUST classify each comparison as significant or
  inconclusive based on the bootstrap distribution, not a point estimate.
- **FR-009**: Regime labels MUST be inferred from observed market features (at
  minimum: realized volatility), not manually supplied.
- **FR-010**: When market feature data is unavailable, regime MUST default to
  "unknown" rather than failing or requiring manual input.
- **FR-011**: The spec-041 contract shapes (`ExpertSignalObservation`,
  `ExpertScorecardSlice`, `ExpertScorecardBundle`) MUST be extended, not replaced.
  Existing top-level fields remain. `dominance_rows` remains the bundle field name;
  its row payloads MAY be tightened to the structured bootstrap-comparison shape as
  a backward-compatible extension of the existing dict-based contract.
- **FR-012**: Observations where the volume-clock window cannot close MUST be marked
  as incomplete with explicit metadata, not silently dropped.
- **FR-013**: The adaptive layer MUST be reproducible: same input data MUST produce
  the same adaptive parameters, buckets, and dominance results.
- **FR-014**: The price path input contract for the adaptive layer MUST be built
  primarily from `klines_1m_history` and MUST include a `volume` field per tick.
  That `volume` field MUST use quote-currency notional (`quote_volume`) for
  cross-symbol comparability. `aggtrades_history` MAY refine touch timing, but it
  is not the primary source for volume-clock closure.
- **FR-014b**: Adaptive primitives that consume `price_path` timestamps MUST accept
  the same timestamp shapes already accepted by the scorecard builder
  (timezone-aware `datetime`, epoch values, and ISO8601 strings) and MUST sort the
  effective path by timestamp before lookback/window slicing.
- **FR-015**: The scorecard MUST continue to work when volume data is absent in the
  price path, falling back to marking volume-clock metrics as unavailable.
- **FR-016**: The liquidation confirmation window MUST close on a volume-based
  criterion (cumulative volume after touch), consistent with the post-touch
  evaluation window (FR-002). A fixed time fallback MAY be retained as secondary
  metadata.
- **FR-017**: The touch scan window (`TOUCH_WINDOW_HOURS`) is classified as a
  computational method parameter, not a market parameter. It defines the maximum
  lookback for touch detection and MAY remain fixed. This is an explicit exception
  to the foundational rule, documented here to avoid ambiguity.
- **FR-017b**: Adaptive touch-band scaling heuristics MAY use documented
  computation-method constants, provided they are not symbol-specific market
  thresholds. MVP freeze:
  `adaptive_band_bps = max(1, floor(local_volatility_bps / 500))`; when realized
  volatility is unavailable, the fallback proxy is
  `max(1, floor(spread_bps / 2))` over the effective normalized pre-snapshot path.
- **FR-017c**: The MVP volume-clock threshold heuristic MAY use documented
  computation-method constants. Freeze:
  `volume_threshold = max(1.0, avg_quote_volume_per_tick * 60)` computed from up to
  the last 1440 eligible `klines_1m_history` ticks before `snapshot_ts`. This is a
  method constant approximating a one-hour quote-volume session, not a
  symbol-specific market threshold.

### Key Entities

- **AdaptiveTouchBand**: Per-symbol, per-timestamp tolerance band derived from local
  volatility. Replaces fixed `TOUCH_TOLERANCE_BPS`.
- **VolumeClockWindow**: Observation window defined by cumulative post-touch volume
  threshold. Replaces fixed `POST_TOUCH_WINDOW_HOURS`.
- **QuantileBucketSet**: Set of bucket boundaries derived from empirical quantiles of
  a given metric (distance_bps, confidence). Replaces hardcoded bucket arrays.
  Implementations MUST enforce a valid contract: positive bucket count, non-negative
  observation count, `len(boundaries) = n_buckets + 1`, `len(labels) = n_buckets`,
  and monotonically non-decreasing boundaries.
- **BootstrapDominanceResult**: Pairwise expert comparison with probability estimate
  and significance classification. Extends the existing `dominance_rows` output with
  a structured bootstrap-comparison payload. Implementations MUST enforce bounded
  probabilities/CI values in `[0,1]`, positive bootstrap count, and
  `ci_lower <= p_a_better <= ci_upper <= 1`.
- **InferredRegime**: Regime label derived from observed market features via
  unsupervised clustering or threshold-free binning.

## Success Criteria

### Measurable Outcomes

- **SC-001**: The scorecard produces different touch tolerance bands for the same
  expert level across different volatility conditions on the same symbol.
- **SC-002**: Post-touch MFE/MAE evaluation uses volume-clock as primary window and
  produces different wall-clock durations for different volume conditions.
- **SC-003**: Distance and confidence bucket boundaries differ across datasets with
  different distributions, and each bucket contains approximately equal observation
  counts (within 2x of the median bucket size).
- **SC-004**: Dominance output includes a pairwise probability and significance
  classification for every expert pair per slice.
- **SC-005**: Regimes are assigned without manual labels and at least two distinct
  regimes emerge from a dataset spanning a known volatility transition.
- **SC-006**: The scorecard remains reproducible: identical inputs produce
  byte-identical outputs.
- **SC-007**: Zero fixed market thresholds, bands, or bucket boundaries remain in
  the adaptive observation layer. Only documented computation-method constants
  (e.g. bootstrap iterations, fixed touch scan cap, quantile count when sufficient
  data exists) may remain.

## Assumptions

- The price path data source can be extended to include per-tick volume/quantity.
  This is available from `aggtrades_history` and `klines` tables in DuckDB.
- Realized volatility can be computed from the price path itself (e.g., rolling
  std of log returns) without requiring an external volatility feed.
- Bootstrap resampling with 1000 iterations is sufficient for dominance CI at MVP.
  This is a computational method parameter, not a market parameter.
- Quantile bucketing with 5 buckets (quintiles) is a reasonable default when
  sufficient data exists. The number of buckets is adaptive, not the quantile
  method itself.

## Glossary

- **Touch scan window**: Maximum time from `snapshot_ts` during which the system
  searches for a price touch. Currently `TOUCH_WINDOW_HOURS`. Method parameter
  (FR-017).
- **Evaluation window**: Post-touch observation period for MFE/MAE computation.
  Closes on volume-clock (adaptive) or `POST_TOUCH_WINDOW_HOURS` (legacy).
- **Confirmation window**: Post-touch period for liquidation event matching.
  Closes on volume-clock (adaptive, FR-016) or `LIQ_CONFIRM_WINDOW_MINUTES`
  (legacy).
