# Data Model: spec-042 Adaptive Observation Layer

## Extended Entities

### ExpertSignalObservation (extended)

New optional fields added to existing contract:

| Field | Type | Description |
|-------|------|-------------|
| `adaptive_touch_band_bps` | `Optional[int]` | Volatility-derived tolerance band used for this observation |
| `local_volatility_bps` | `Optional[int]` | Realized volatility at snapshot_ts in bps (annualized) |
| `volume_at_touch` | `Optional[float]` | Cumulative volume from snapshot_ts to touch_ts |
| `volume_window_complete` | `Optional[bool]` | Whether volume-clock window closed normally |
| `post_touch_volume` | `Optional[float]` | Cumulative volume in post-touch evaluation window |
| `inferred_regime` | `Optional[str]` | Data-derived regime label for this observation |

All existing fields remain unchanged. New fields default to `None`.

### ExpertScorecardSlice (extended)

New optional fields:

| Field | Type | Description |
|-------|------|-------------|
| `bucket_boundaries` | `Optional[Dict[str, Any]]` | The quantile boundaries used for this slice |

### ExpertScorecardBundle (extended)

New optional fields:

| Field | Type | Description |
|-------|------|-------------|
| `adaptive_parameters` | `Optional[Dict[str, Any]]` | Computed adaptive parameters (vol, bands, bucket boundaries) |

### BootstrapDominanceResult (structured dominance_rows payload)

The bundle field name remains `dominance_rows`. Under adaptive mode, each row uses
this structured payload:

| Field | Type | Description |
|-------|------|-------------|
| `comparison_slice_id` | `str` | Slice dimensions key |
| `expert_a` | `str` | First expert in comparison |
| `expert_b` | `str` | Second expert in comparison |
| `metric` | `str` | Metric being compared (touch_probability, liq_match_prob, mfe_p50, mae_p50) |
| `p_a_better` | `float` | Bootstrap probability that expert_a > expert_b |
| `significant` | `bool` | Whether CI excludes 0.5 |
| `ci_lower` | `float` | Lower bound of 95% CI |
| `ci_upper` | `float` | Upper bound of 95% CI |
| `n_bootstrap` | `int` | Number of bootstrap iterations used |

Contract invariants:
- `0 <= p_a_better <= 1`
- `0 <= ci_lower <= ci_upper <= 1`
- `ci_lower <= p_a_better <= ci_upper`
- `n_bootstrap > 0`

## New Entities

### AdaptiveTouchBand

Not a persisted entity — computed per observation at runtime.

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | Symbol for which band was computed |
| `timestamp` | `datetime` | Observation timestamp |
| `band_bps` | `int` | Computed tolerance band in bps |
| `local_vol_bps` | `int` | Input: local realized volatility |
| `method` | `str` | Computation method identifier |

### VolumeClockWindow

Not persisted — computed per touched observation.

| Field | Type | Description |
|-------|------|-------------|
| `volume_threshold` | `float` | Cumulative volume at which window closes |
| `volume_consumed` | `float` | Actual volume consumed before close |
| `closed_normally` | `bool` | Whether threshold was reached |
| `wall_clock_duration_secs` | `Optional[int]` | Actual wall-clock time elapsed |

### QuantileBucketSet

Computed once per pipeline run from the full observation set.

| Field | Type | Description |
|-------|------|-------------|
| `metric_name` | `str` | "distance_bps" or "confidence" |
| `n_buckets` | `int` | Number of buckets (adaptive) |
| `boundaries` | `list[float]` | Quantile boundary values |
| `labels` | `list[str]` | Human-readable bucket labels |
| `observation_count` | `int` | Total observations used to derive boundaries |

Contract invariants:
- `n_buckets > 0`
- `observation_count >= 0`
- `len(boundaries) = n_buckets + 1`
- `len(labels) = n_buckets`
- `boundaries` are monotonically non-decreasing

### InferredRegimeMap

Computed once per pipeline run.

| Field | Type | Description |
|-------|------|-------------|
| `method` | `str` | "volatility_quantile" |
| `n_regimes` | `int` | Number of distinct regimes assigned |
| `regime_labels` | `list[str]` | Labels assigned (e.g., "low_vol", "high_vol") |
| `vol_boundaries` | `list[float]` | Volatility quantile boundaries |

## Price Path Contract Extension

Current: `{"timestamp": <ts>, "price": <float>}`

Extended: `{"timestamp": <ts>, "price": <float>, "volume": <float>}`

`volume` is optional. When absent, volume-clock metrics are marked unavailable
(FR-015).

Adaptive primitives consuming `timestamp` MUST accept the same shapes as the
scorecard builder contract: timezone-aware `datetime`, epoch values, and ISO8601
strings. Effective price paths are normalized and sorted by timestamp before
lookback/window slicing.

## State Transitions

No state machines in this spec. All computations are pure functions:
input data → adaptive parameters → observations → slices → bundle.
