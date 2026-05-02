# Research: spec-042 Adaptive Observation Layer

## R1: Volume Data Availability

**Decision**: Extend price path dict to include optional `volume` field from
`klines_1m_history.quote_volume`.

**Rationale**: klines tables already have `volume`, `quote_volume`, `taker_buy_volume`,
`taker_buy_quote_volume`. aggtrades has per-trade `quantity` and `gross_value`. The
price path structure (`{"timestamp", "price"}`) just needs a `"volume"` field added.
`klines_1m_history` is the natural source: one tick per minute with quote notional
volume already aggregated.

**Alternatives considered**:
- aggtrades tick-level: too granular, 6B+ rows, DuckDB scan too expensive
- klines_5m: coarser but less precise volume-clock resolution
- External volume feed: unnecessary, data is already in DuckDB

## R1b: Volume Field Selection

**Decision**: Use `quote_volume` (notional) as the primary volume metric.

**Rationale**: `quote_volume` (price * quantity in quote currency) normalizes across
symbols — 1 BTC traded and 100 ETH traded become comparable in USDT terms. Raw
`volume` (base asset quantity) is not comparable cross-symbol. `taker_buy_volume`
is a subset and would undercount.

**For price path construction**: When building price path from `klines_1m_history`, use
`quote_volume` as the `"volume"` field value.

**Alternatives considered**:
- `volume` (base): not comparable cross-symbol
- `taker_buy_volume`: subset, underestimates total activity
- `gross_value` from aggtrades: per-trade, needs aggregation

## R2: Volatility Computation

**Decision**: Compute realized volatility from log-returns of klines close prices.

**Rationale**: No volatility code exists in the codebase. The simplest non-parametric
approach is rolling standard deviation of log-returns: `std(log(close[t]/close[t-1]))`.
This is computed from the same price path used for touch detection. The lookback
window is itself data-driven: use the inter-quartile range of recent log-return
magnitudes to determine a stable lookback.

For MVP, a fixed lookback of 60 klines (1h of 1m candles) is acceptable as a
*computational method parameter* (it defines the estimation window, not a market
threshold). The *output* — the volatility value — is fully data-derived.

**Alternatives considered**:
- ATR (Average True Range): requires high/low/close, more complex, no clear benefit
- Parkinson/Garman-Klass estimators: more efficient but add complexity without clear MVP need
- External vol feed: adds dependency, violates KISS

## R3: Bootstrap Resampling

**Decision**: Implement bootstrap resampling from scratch using Python stdlib `random`.

**Rationale**: No bootstrap code exists. The computation is simple: resample
observations with replacement N times, compute the metric each time, derive CI
from the distribution. Using stdlib `random` with a fixed seed ensures
reproducibility (FR-013). No external dependency needed.

Bootstrap parameters:
- `n_bootstrap = 1000` — computational method parameter, not a market parameter
- `seed` — deterministic per comparison key for reproducibility
- `higher_is_better` — explicit metric orientation; use `False` for lower-is-better
  metrics such as `mae_p50`
- CI threshold: if 95% CI of `P(A > B)` includes 0.5, mark inconclusive

**Alternatives considered**:
- scipy.stats.bootstrap: adds scipy dependency
- numpy random: adds numpy dependency for a trivial operation
- Bayesian posterior: overengineered for MVP

## R4: Quantile Bucketing

**Decision**: Replace hardcoded bucket boundaries with empirical quantile boundaries.

**Rationale**: Existing `_compute_quantiles()` in aggregator.py computes percentiles
with linear interpolation. The same function can compute bucket boundaries from the
full observation set before slicing. Default to quintiles (5 buckets) when ≥25
observations exist; fall back to a single "all" bucket when data is sparse.

Bucket labels are stable quantile names (`"q1"`, `"q2"`, ...). Numeric boundaries
are retained separately in `bucket_boundaries` and `adaptive_parameters`.

**Alternatives considered**:
- DBSCAN clustering: overkill for 1D bucketing
- Fixed number of equal-width bins: violates Non Lineare (ignores distribution shape)
- Jenks natural breaks: interesting but adds complexity, defer to future

## R5: Regime Inference

**Decision**: Infer regime from realized volatility quantiles of the observation window.

**Rationale**: The simplest non-parametric regime assignment is: compute realized
volatility for each observation's timestamp window, then assign regime labels based
on the empirical quantile of that volatility value within the full dataset. E.g.,
below median vol → "low_vol", above → "high_vol". With more data, use terciles or
quartiles.

This requires no clustering library, no manual labels, and adapts as new data
arrives. The regime boundaries are themselves data-derived (quantiles of the
vol distribution).

**Alternatives considered**:
- k-means clustering on multiple features: more powerful but adds sklearn dependency
  and complexity; defer to later spec
- Hidden Markov Model: parametric, violates Non Parametrico
- Manual labels: violates the foundational rule
- Multi-feature clustering (vol + OI + funding): defer until single-feature regime
  proves useful

## R6: Reusable Assets

| Asset | Location | Reuse Strategy |
|-------|----------|----------------|
| `_compute_quantiles()` | `aggregator.py:9-37` | Use directly for bucket boundaries and vol quantiles |
| Slice ID generation | `scorecard.py:104-115` | Keep unchanged, bucket labels change |
| Aggregation pipeline | `aggregator.py:40-95` | Keep unchanged |
| Regime map interface | `slicer.py:16-17` | Replace manual map with auto-computed map |
| klines volume schema | `gap_fill.py:36-55` | Source for volume data |

## R7: What NOT to Change

- `ExpertSignalObservation` fields — extend with optional new fields, don't remove
- `ExpertScorecardSlice` fields — extend, don't remove
- `ExpertScorecardBundle` shape — extend, don't remove
- Pipeline `run()` signature — add optional parameters, don't break existing
- Deterministic ID contracts — keep UUID5 and slice_id format
