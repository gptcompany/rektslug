# Handoff: spec-032 Canonical Liq-Map Product Hardening

## Status

Implemented.

`spec-032` freezes the current canonical `liq-map` product boundary and makes
public-vs-legacy routing explicit across validation, capture, comparison, and
calibration workflows.

## Frozen Product Boundary

The canonical browser route remains:

- `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}`

The canonical public API matrix is:

| Exchange | Public API |
|----------|------------|
| Binance | `/liquidations/coinank-public-map` |
| Bybit | `/liquidations/coinank-public-map` |
| Hyperliquid | `/liquidations/hl-public-map` |

The legacy API surface remains:

- `/liquidations/levels`

The legacy surface is kept for calibration and internal model inspection only.
It is not the canonical product surface. Hyperliquid has no legacy liq-map
surface in this spec.

## Machine-Readable Provenance

Workflow artifacts now preserve route selection with:

- `requested_surface`
- `effective_surface`
- `effective_api_endpoint_path`

Binance and Bybit public map responses now preserve serving provenance with:

- `serving_provenance`: `artifact-backed`, or `legacy-fallback` for Binance fallback serving
- `serving_artifact_model_id`: artifact model id when artifact-backed, else `null`
- `serving_artifact_snapshot_ts`: artifact snapshot timestamp when artifact-backed, else `null`

Use `serving_provenance` to distinguish a Binance public response served from a
modeled snapshot artifact from the public route's legacy fallback builder.

## Implementation Touchpoints

- `scripts/validate_liqmap_visual.py`
- `scripts/run_visual_harness.py`
- `src/liquidationheatmap/validation/visual_harness/runner.py`
- `src/liquidationheatmap/validation/visual_harness/manifest.py`
- `src/liquidationheatmap/validation/visual_harness/providers/local.py`
- `scripts/capture_provider_api.py`
- `scripts/run_provider_api_comparison.py`
- `scripts/compare_provider_liquidations.py`
- `scripts/provider_gap_analysis.py`
- `scripts/run_ank_calibration.py`
- `scripts/run_glass_calibration.py`
- `src/liquidationheatmap/api/public_liqmap.py`

## Validation Coverage

The relevant coverage is in:

- `tests/test_visual/test_liqmap_visual.py`
- `tests/test_scripts/test_run_visual_harness.py`
- `tests/unit/validation/test_visual_harness/test_runner.py`
- `tests/test_capture_provider_api.py`
- `tests/test_provider_comparison_workflow.py`
- `tests/test_run_ank_calibration.py`
- `tests/test_run_glass_calibration.py`
- `tests/unit/api/test_coinank_public_map_builder.py`
- `tests/contract/test_coinank_public_map.py`
- `tests/integration/test_bybit_public_map.py`
- `tests/integration/test_liqmap_frontend_visual.py`

## Follow-Up Tracks

These are intentionally out of scope for `spec-032`:

- Provider-parity math and provider-specific public builder modes such as `model=coinank|coinglass`.
- Coinglass-style public map parity on the canonical route.
- Liquidation heatmap work under `/chart/derivatives/liq-heat-map/...`.
- Removal of legacy `/liquidations/levels`.
