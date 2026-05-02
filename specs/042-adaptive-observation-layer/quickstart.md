# Quickstart: spec-042 Adaptive Observation Layer

## Prerequisites

- spec-041 scorecard fully implemented and tests green
- DuckDB with `klines_1m_history` populated (use `quote_volume` as the adaptive
  price-path `volume` field)
- Python 3.10+, uv

## Run Tests

```bash
uv run pytest tests/test_scorecard/ -v
```

## Run Adaptive Scorecard

```python
from src.liquidationheatmap.scorecard.pipeline import ScorecardPipeline

pipeline = ScorecardPipeline()

# Load artifacts (same as spec-041)
artifacts = pipeline.load_retained_artifacts(
    symbols=["BTCUSDT"],
    expert_ids=["v1", "v3", "v4", "v5"],
    limit_manifests=10,
)

# Price path with quote-notional volume (new requirement)
price_path = [
    {"timestamp": "2026-05-01T00:00:00Z", "price": 95000.0, "volume": 1200000.0},
    {"timestamp": "2026-05-01T00:01:00Z", "price": 95010.0, "volume": 830000.0},
    # ...
]

liquidation_events = [...]

# Adaptive mode (new)
bundle_json = pipeline.run(
    artifacts=artifacts,
    price_path=price_path,
    liquidation_events=liquidation_events,
    expected_experts=["v1", "v3", "v4", "v5"],
    enable_adaptive=True,  # activates all adaptive features
)

# Backward compatible mode (identical to spec-041)
bundle_json_legacy = pipeline.run(
    artifacts=artifacts,
    price_path=price_path,
    liquidation_events=liquidation_events,
    expected_experts=["v1", "v3", "v4", "v5"],
    enable_adaptive=False,  # default, same as spec-041
)
```

## Key Differences from spec-041

| Aspect | spec-041 | spec-042 (adaptive) |
|--------|----------|---------------------|
| Touch tolerance | 5 bps fixed | f(local_vol) |
| Post-touch window | 1h fixed | volume-clock |
| Distance buckets | [0-25, 25-50, ...] | empirical quantiles |
| Confidence buckets | [0.0-0.3, ...] | empirical quantiles |
| Dominance | winner-takes-all | bootstrap P(A>B) + CI |
| Regime | manual or "none" | inferred from vol quantiles |

For lower-is-better metrics such as `mae_p50`, adaptive dominance uses explicit
metric orientation before computing `P(A better than B)`.

## File Layout

```
src/liquidationheatmap/scorecard/
├── __init__.py          # existing
├── builder.py           # extended: adaptive touch band, volume-clock
├── aggregator.py        # existing (reused)
├── slicer.py            # extended: quantile buckets, inferred regime
├── pipeline.py          # extended: enable_adaptive flag
├── adaptive.py          # NEW: vol computation, adaptive bands, quantile buckets
└── bootstrap.py         # NEW: bootstrap resampling, dominance CI
```
