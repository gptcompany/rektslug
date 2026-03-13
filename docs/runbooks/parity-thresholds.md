# Parity Thresholds

This runbook is the single source of truth for parity gates across:

- visual similarity
- provider-data calibration
- future heatmap work

It intentionally separates those categories because they do **not** share the
same scoring model.

## 1. Liq-Map Visual Thresholds

Status: **active**

Applies to:

- `rektslug vs CoinAnK`
- `rektslug vs Coinglass`
- product `liq-map`
- renderer `plotly`
- harness `scripts/run_visual_harness.py`

### Official Gate

- default `pass_threshold = 95`
- accepted CLI override range: `90..100`
- recommended production/manual gate: `95`
- recommended exploratory/diagnostic gate: `90`

### Pass Rule

A visual comparison pair passes only when:

- `tier1_pass = true`
- `score >= pass_threshold`

For the frozen MVP contract:

- Tier-1 failure forces total `score = 0`
- `max_score = 100`

### Scope Limit

These thresholds currently apply only to the frozen `liq-map + plotly` path.
They do **not** automatically apply to `liq-heat-map` or `lightweight`.

## 2. Liq-Map Data Calibration Thresholds

Status: **active**

Applies to:

- `spec-018` (`rektslug-ank`)
- `spec-019` (`rektslug-glass`)
- product `liq-map`
- provider-comparison workflow, not the visual harness

### Important Distinction

Data calibration does **not** use a single `95/100` score.
It uses improvement-based acceptance on a frozen matrix:

- symbols: `BTCUSDT`, `ETHUSDT`
- timeframes: `1d`, `1w`
- matrix size: `4` entries

### Shared Acceptance Rule

A calibrated profile is accepted only if it:

- improves at least `3/5` core metrics
- on at least `3/4` matrix entries
- with no critical regression above `30%` on any entry

### Core Metrics

The active core metrics are:

1. bucket-count proximity
2. long/short total ratio
3. long/short peak ratio
4. current-price anchor
5. bucket overlap on aligned grid

### Provider-Specific Improvement Gates

#### CoinAnK / `rektslug-ank`

Source of truth: [spec-018](../../specs/018-rektslug-ank-calibration/spec.md)

- bucket-count proximity: reduce baseline gap by `>= 20%`
- long/short total ratio: reduce baseline gap by `>= 15%`
- long/short peak ratio: reduce baseline gap by `>= 15%`
- current-price anchor: reduce baseline gap by `>= 10%`
- bucket overlap: increase baseline overlap by `>= 10%`

#### Coinglass / `rektslug-glass`

Source of truth: [spec-019](../../specs/019-rektslug-glass-calibration/spec.md)

- bucket-count proximity: reduce baseline gap by `>= 20%`
- long/short total ratio: reduce baseline gap by `>= 15%`
- long/short peak ratio: reduce baseline gap by `>= 15%`
- current-price anchor: reduce baseline gap by `>= 10%`
- bucket overlap: increase baseline overlap by `>= 5%`

Coinglass uses the lighter `bucket_overlap` gate because its `liqMap` payload
clusters state under top-level price buckets, so overlap improves in smaller
steps than the CoinAnK path.

## 3. Heatmap Thresholds

Status: **not frozen yet**

Applies to:

- future `liq-heat-map` visual parity
- future `liq-heat-map` data parity

### Current Rule

No official `90` or `95` threshold is frozen yet for heatmaps.

Reason:

- the harness seams exist
- the product-specific live path is not yet finalized
- renderer behavior and scoring semantics are still expected to diverge from
  the current `liq-map + plotly` contract

### Temporary Guidance

Until heatmap scoring is frozen:

- do **not** reuse the `95` visual gate as a claimed production threshold
- do **not** report heatmap parity as "green" using only liq-map criteria
- define explicit heatmap thresholds in the future heatmap spec before using
  pass/fail language

## 4. Practical Use

Use this matrix when deciding which gate to apply:

| Surface | Threshold model | Official gate |
|---------|------------------|---------------|
| `liq-map` visual harness | score out of 100 | `95` default, `90` minimum override |
| `liq-map` CoinAnK calibration | improvement-based | `3/5` metrics on `3/4` entries, no `>30%` regression |
| `liq-map` Coinglass calibration | improvement-based | `3/5` metrics on `3/4` entries, no `>30%` regression |
| `liq-heat-map` visual/data | not frozen yet | TBD |

## 5. References

- [Provider API Comparison Workflow](../provider-api-comparison.md)
- [Chart Routes](chart-routes.md)
- [Spec 018](../../specs/018-rektslug-ank-calibration/spec.md)
- [Spec 019](../../specs/019-rektslug-glass-calibration/spec.md)
- [Spec 020](../../specs/020-visual-comparison-harness/spec.md)
