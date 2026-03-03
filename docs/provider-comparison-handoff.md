# Provider Comparison Handoff

## Scope

This handoff is only for the `provider-comparison` track.

It does **not** cover the separate `ingestion-lock` / `gap-fill` track.

## Commit Checkpoint

The provider-comparison work is captured in:

- `621b542` `feat: add provider gap analysis and bundle drift reporting`
- `172352e` `feat: add internal provider benchmark comparisons`
- `b18a3e6` `fix: restore wrappers and prioritize shape-first benchmarks`

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
- internal-vs-vendor benchmark scenarios
- shape-first benchmark summary (`internal_alignment`)

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

- `data/validation/provider_comparisons/20260303T203530Z_provider_gap_analysis.json`

Current method:

- primary metrics: `shape_cosine`, `distribution_overlap`, `matched_bucket_ratio`
- secondary metrics: `vendor_scale_factor`, `total_ratio`

Current best internal benchmark basis:

- internal `time_window=48h`
- internal `price_bin_size=57`

Interpretation:

- shape is currently closer to `Coinglass` than `CoinAnk`
- `internal -> Coinglass`: `shape_cosine=0.3545`, `overlap=0.2187`, `scale_factor=13.47`
- `internal -> CoinAnk`: `shape_cosine=0.1832`, `overlap=0.1338`, `scale_factor=180.99`
- vendor totals are treated as scaling profiles, not as directly equivalent ground truth

## Useful Commands

Rebuild the scenario analysis from a capture manifest:

```bash
python3 scripts/provider_gap_analysis.py \
  --manifest data/validation/raw_provider_api/<timestamp>/manifest.json \
  --internal-time-window 48h \
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

Quick sanity check:

```bash
python3 scripts/provider_gap_analysis.py \
  --manifest data/validation/raw_provider_api/20260303T174430Z/manifest.json \
  --internal-time-window 48h \
  --output /tmp/check.json
```

```bash
jq '.internal_alignment' /tmp/check.json
```

## Next Useful Step

If this track is resumed, the next useful step is not more capture plumbing.

The useful next step is:

1. Tune the internal model for better shape vs `Coinglass` first
2. Keep scale as a separate vendor-specific multiplier
3. Only after shape improves, revisit absolute totals
