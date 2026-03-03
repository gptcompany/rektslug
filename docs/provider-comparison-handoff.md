# Provider Comparison Handoff

## Scope

This handoff is only for the `provider-comparison` track.

It does **not** cover the separate `ingestion-lock` / `gap-fill` track.

## Commit Checkpoint

The provider-comparison work is captured in:

- `621b542` `feat: add provider gap analysis and bundle drift reporting`

The current branch head already includes that commit.

## What Was Added

- `scripts/provider_gap_analysis.py`
- `scripts/provider_gap_sql_report.py`
- `scripts/coinglass_bundle_report.py`

Also updated:

- `scripts/compare_provider_liquidations.py`
- `docs/provider-api-comparison.md`

## Core Outcome

The CoinAnk vs Coinglass comparison is now persisted in the validation DuckDB,
not just in ad-hoc JSON reports.

Main additions:

- scenario-based gap analysis
- SQL report over gap-analysis tables
- local CoinGlass bundle hash / marker drift report

## DuckDB Tables

Stored in:

- `data/validation/validation_results.duckdb`

New tables:

- `provider_gap_analysis_runs`
- `provider_gap_analysis_scenarios`
- `provider_gap_analysis_leverage`
- `coinglass_bundle_observations`

## Current Baseline

Use this report as the current baseline:

- `data/validation/provider_comparisons/20260303T181518Z_provider_gap_analysis.json`

Key numbers from that run:

- `raw` total ratio: `13.4318x`
- `coinank_common_tiers` total ratio: `5.2566x`
- `coinank_rebinned_to_coinglass_step` total ratio: `13.4318x`
- `coinank_common_tiers_rebinned` total ratio: `5.2566x`

Current best comparison basis:

- `coinank_common_tiers_rebinned`

Interpretation:

- leverage-tier coverage explains most of the raw gap
- price-bin granularity changes shape, not scale
- residual gap (`~5.26x`) likely comes from provider-side aggregation /
  persistence / scaling differences

## Useful Commands

Rebuild the scenario analysis from a capture manifest:

```bash
python3 scripts/provider_gap_analysis.py \
  --manifest data/validation/raw_provider_api/<timestamp>/manifest.json \
  --persist-db
```

Query historical gap-analysis runs from DuckDB:

```bash
python3 scripts/provider_gap_sql_report.py
```

Check the local CoinGlass bundle for TOTP/AES drift:

```bash
python3 scripts/coinglass_bundle_report.py --persist-db
```

## CoinGlass Bundle Checkpoint

Most recent observed bundle during this session:

- path: `/tmp/_app-94ee9e72c1d2190a.js`
- sha256: `9f4a6ed5ff66bb56bc380004b334ec6f31c9c2869b8b4c9e1033c531ee02a511`

At that checkpoint:

- TOTP secret marker present
- AES key marker present
- liqMap endpoint marker present

## Next Useful Step

If this track is resumed, the next useful step is not more capture plumbing.

The useful next step is:

1. Compare multiple runs over time with `provider_gap_sql_report.py`
2. Check whether the `~5.26x` residual gap is stable across timeframes/runs
3. Only then decide whether an extra normalization layer is justified
