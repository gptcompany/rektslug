# Adaptive Scorecard Internal API Contract

## Pipeline Entry Points

### `ScorecardPipeline.run()` (extended)

Existing signature preserved. New optional parameters:

```
run(
    artifacts: list[dict],
    price_path: list[dict],          # now supports optional "volume" per tick
    liquidation_events: list[dict],
    expected_experts: list[str],
    # NEW optional parameters:
    enable_adaptive: bool = False,   # opt-in to adaptive layer
) -> str                             # JSON bundle
```

When `enable_adaptive=True`:
- Touch tolerance is volatility-derived (not 5 bps)
- Post-touch window is volume-clock (not 1h)
- Buckets are quantile-derived (not hardcoded)
- Dominance uses bootstrap CI (not point estimates)
- Regime is inferred (not manual)

When `enable_adaptive=False` (default):
- Behavior identical to spec-041 for backward compatibility

### `ScorecardPipeline.run_from_retained_snapshots()` (extended)

Same pattern: `enable_adaptive` parameter added, forwarded to `run()`.

## New Module: `src/liquidationheatmap/scorecard/adaptive.py`

### `compute_adaptive_touch_band(price_path, snapshot_ts, symbol) -> int`

Returns touch tolerance in bps derived from local realized volatility.

### `compute_volume_threshold(price_path, snapshot_ts) -> float`

Returns cumulative volume threshold for observation window closure.

### `compute_quantile_buckets(values, metric_name, min_per_bucket) -> QuantileBucketSet`

Returns data-derived bucket boundaries from empirical quantiles.

### `compute_realized_volatility(price_path, timestamp, lookback_ticks) -> int`

Returns realized vol in bps from rolling log-return std.

### `infer_regime_map(observations, price_path) -> dict[datetime, str]`

Returns regime label per timestamp from volatility quantiles.

## New Module: `src/liquidationheatmap/scorecard/bootstrap.py`

### `bootstrap_dominance(obs_a, obs_b, metric_fn, n_bootstrap, seed, higher_is_better=True) -> BootstrapDominanceResult`

Returns pairwise comparison with probability and CI. `higher_is_better=False` is
required for metrics where lower values are better, such as `mae_p50`.

## Bundle Output Extension

The JSON bundle retains all spec-041 top-level fields. `dominance_rows` remains the
field name for backward compatibility. New fields when adaptive is enabled:

```json
{
  "slices": [...],
  "dominance_rows": [
    {
      "comparison_slice_id": "BTCUSDT:long:q1:high:low_vol",
      "expert_a": "v1",
      "expert_b": "v3",
      "metric": "touch_probability",
      "p_a_better": 0.73,
      "significant": false,
      "ci_lower": 0.41,
      "ci_upper": 0.89,
      "n_bootstrap": 1000
    }
  ],
  "adaptive_parameters": {
    "volume_threshold": 1500000.0,
    "regime_method": "volatility_quantile",
    "distance_buckets": {
      "metric_name": "distance_bps",
      "n_buckets": 5,
      "boundaries": [0, 45, 112, 230, 510, 900],
      "labels": ["q1", "q2", "q3", "q4", "q5"],
      "observation_count": 1000
    },
    "confidence_buckets": {
      "metric_name": "confidence",
      "n_buckets": 5,
      "boundaries": [0.0, 0.22, 0.51, 0.78, 0.91, 1.0],
      "labels": ["q1", "q2", "q3", "q4", "q5"],
      "observation_count": 1000
    }
  },
  "coverage_gaps": {...},
  "retained_input_range": {...},
  "artifact_provenance": {...}
}
```
