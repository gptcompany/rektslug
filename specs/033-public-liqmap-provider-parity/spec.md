# Feature Specification: Public Liq-Map Provider Parity

**Feature Branch**: `033-public-liqmap-provider-parity`
**Created**: 2026-04-11
**Status**: Draft
**Dependencies**: spec-017 (provider comparison), spec-020 (visual harness), spec-022 (CoinAnK public data path), spec-026 (model-calibration findings), spec-030 (modeled snapshots), spec-031 (Binance/Bybit public serving), spec-032 (public/legacy surface hardening)

## Context

`spec-032` closed the surface ambiguity problem. The canonical browser product is:

- `/chart/derivatives/liq-map/{exchange}/{symbol}/{timeframe}`

and product-facing local validation now defaults to `surface=public`.

The next gap is model parity. The public route is wired and instrumented, but it
does not yet guarantee that the public payload is close to the reference provider
map that users expect.

The historical provider-comparison evidence shows why this cannot be solved by
one blind "make it bigger" multiplier:

- CoinAnK and Coinglass do not agree on absolute scale.
- CoinAnK and Coinglass do not always agree on normalized shape.
- Rektslug's legacy local model historically diverged on scale, bucket density,
  grid step, and long/short ratio.
- The current artifact-backed public adapter can serve a modeled snapshot, but
  the response bridge still spreads aggregate distribution across leverage tiers
  for display richness rather than preserving a proven provider-specific ladder.

This spec defines the provider-parity work that `spec-032` intentionally left
out.

## Goal

Make the canonical public `liq-map` product measurable and tunable against
provider references, with CoinAnK as the default product reference and Coinglass
as an explicit secondary reference profile.

The goal is not to claim that CoinAnK or Coinglass is ground truth. The goal is
to make Rektslug's public map behavior explicit, repeatable, and closer to the
chosen reference provider than the current generic model.

## Product Decision

This spec makes the following product decisions:

1. The public product remains `surface=public`.
2. There is no third surface.
3. Provider parity is modeled as a public-route profile axis, not as a surface.
4. The default public reference is `coinank`.
5. `coinglass` is a secondary, explicit reference profile because its scale and
   shape semantics differ materially from CoinAnK.
6. Binance is the first parity target. Bybit and Hyperliquid must not be allowed
   to regress, but they are not the first signoff target for this spec.
7. Heatmap work remains out of scope.

## Scope

### In Scope

- Refresh a baseline using `surface=public` for `binance` on:
  - `BTCUSDT x 1d`
  - `BTCUSDT x 1w`
  - `ETHUSDT x 1d`
  - `ETHUSDT x 1w`
- Compare public Rektslug against:
  - CoinAnK `getLiqMap` as the primary reference
  - Coinglass Binance per-exchange `liqMap` as a secondary reference
- Define a provider-parity profile axis for the public builder:
  - `reference_provider=coinank`
  - `reference_provider=coinglass`
- Preserve `reference_provider=coinank` as the default public product behavior.
- Add machine-readable parity metadata to public responses and validation
  artifacts.
- Define and implement numeric provider-parity metrics for shape, scale, grid,
  long/short balance, and peak alignment.
- Tune the Binance public model so the CoinAnK profile is measurably closer to
  CoinAnK on the frozen `BTC/ETH x 1d/1w` matrix.
- Keep the current browser URL contract and public endpoint contract stable.

### Out of Scope

- `liq-heat-map` / liquidation heatmap parity.
- Coinglass `LiquidityHeatmap` or `LiquidationHeatMapNew` 2D grid parity.
- Treating CoinAnK and Coinglass as one blended target.
- Exact 1:1 claims against providers.
- Hyperliquid CoinGlass top-position parity; that remains governed by spec-026
  and `/liquidations/hl-public-map`.
- Bybit provider-parity signoff before Binance public parity is green.
- Removing legacy `/liquidations/levels`.

## Reference Matrix

### Local Public Routes

- `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`

### Public API

Current endpoint:

- `/liquidations/coinank-public-map?exchange=binance&symbol={symbol}&timeframe={timeframe}`

This endpoint name is retained for compatibility even when a secondary
`reference_provider=coinglass` profile is added.

### Provider References

CoinAnK primary:

- `https://api.coinank.com/api/liqMap/getLiqMap?exchange=Binance&symbol={symbol}&interval={timeframe}`
- public page route:
  `/chart/derivatives/liq-map/binance/{symbol_lower}/{timeframe}`

Coinglass secondary:

- page target: `https://www.coinglass.com/pro/futures/LiquidationMap`
- endpoint family: `https://capi.coinglass.com/api/index/5/liqMap`
- Binance per-exchange symbol mapping:
  - `BTCUSDT -> Binance_BTCUSDT`
  - `ETHUSDT -> Binance_ETHUSDT`
- timeframe mapping:
  - `1d -> interval=1, limit=1500`
  - `1w -> interval=5, limit=2000`

## Provider Profiles

### `reference_provider=coinank`

CoinAnK is the default public reference profile.

The profile should preserve these semantics:

- exchange-specific Binance public map
- symbol-specific `getLiqMap` reference
- leverage ladder starts at `25x` and excludes `5x` / `10x`
- price grid should follow the provider's effective step for the symbol/timeframe
- totals are treated as USD-notional
- long/short split is evaluated around the provider pivot (`lastIndex` or
  current-price fallback)

### `reference_provider=coinglass`

Coinglass is an explicit secondary profile, not the default product behavior.

The profile should preserve these semantics:

- Binance per-exchange reference, not aggregated-market reference
- `liqMapV2` cluster payload, not heatmap endpoints
- different bucket density and effective grid step from CoinAnK
- totals treated as USD-notional based on endpoint semantics and magnitude
- lower absolute scale than CoinAnK in the observed baseline

## API Contract Additions

The public endpoint MUST accept:

- `reference_provider`: enum `{coinank, coinglass}`, default `coinank`

The public response MUST expose:

- `reference_provider`
- `parity_model_id`
- `parity_model_version`
- `parity_calibration_id`
- `serving_provenance`
- `serving_artifact_model_id`
- `serving_artifact_snapshot_ts`

`serving_provenance` remains the source-serving provenance from `spec-032`.
`reference_provider` is the intended parity target. These are different fields
and MUST NOT be conflated.

## Calibration Artifact Contract

Any accepted calibration coefficients MUST be persisted in a versioned artifact
instead of being embedded as silent constants.

Canonical artifact path:

- `data/validation/public_liqmap_provider_parity/calibrations/{calibration_id}.json`

Minimum calibration artifact fields:

- `calibration_id`
- `reference_provider`
- `exchange`
- `matrix_entries`
- `source_report_ids`
- `created_at`
- `parity_model_id`
- `parity_model_version`
- `coefficients`
- `metric_contract_version`
- `acceptance_summary`

The public response `parity_calibration_id` MUST point to this artifact when a
non-default calibration is applied. Reports MUST include the calibration id and
source report ids so a later run can audit or roll back a tuning decision.

## Metrics Contract

Every provider-parity report MUST include at least:

- `reference_provider`
- `exchange`
- `symbol`
- `timeframe`
- `requested_surface`
- `effective_surface`
- `effective_api_endpoint_path`
- `serving_provenance`
- `serving_artifact_model_id`
- `serving_artifact_snapshot_ts`
- `total_long`
- `total_short`
- `long_short_ratio`
- `bucket_count`
- `price_step_median`
- `peak_long_price`
- `peak_short_price`
- `total_scale_ratio`
- `long_short_ratio_delta`
- `bucket_count_ratio`
- `price_step_ratio`
- `normalized_overlap`
- `normalized_wasserstein`
- `pearson_r`
- `top_peak_hit_rate`

Reports MUST distinguish provider-data failure from local-model failure. Missing
provider capture must not be interpreted as a passing local model.

## Metric Math Contract

All metric calculations MUST be deterministic and testable on fixed inputs.

Precision policy:

- Monetary totals, ratios, and score inputs MUST use `Decimal` or an equivalent
  fixed-precision type internally.
- JSON report serialization MAY emit numbers as JSON numbers, but the report
  MUST preserve enough decimal precision to reproduce pass/fail decisions.
- Price-bucket alignment MUST use an explicit grid step and deterministic
  rounding mode. The initial rounding mode is half-up to the nearest effective
  local grid step unless a provider parser supplies exact bucket keys.

Definitions:

- `long_total = sum(long_bucket.volume)`
- `short_total = sum(short_bucket.volume)`
- `total_volume = long_total + short_total`
- `long_short_ratio = long_total / short_total` when `short_total > 0`, else
  `null` and Tier 1 failure
- `total_scale_ratio = local.total_volume / provider.total_volume` when
  `provider.total_volume > 0`, else `null` and Tier 1 failure
- `long_short_ratio_delta = abs(local.long_short_ratio - provider.long_short_ratio)`
  when both ratios are present, else `null` and Tier 1 failure
- `bucket_count_ratio = local.bucket_count / provider.bucket_count` when
  `provider.bucket_count > 0`, else `null` and Tier 1 failure
- `price_step_ratio = local.price_step_median / provider.price_step_median` when
  `provider.price_step_median > 0`, else `null` and Tier 1 failure
- `normalized_overlap = sum(min(local_i, provider_i))` after both distributions
  are rebinned to the comparison grid and normalized to sum to `1.0`
- `normalized_wasserstein` is the 1D earth-mover distance over the same normalized
  rebinned price distribution, divided by the provider price span
- `pearson_r` is computed on the same rebinned normalized vectors; if either
  vector has zero variance, report `null` and fail the shape component
- `top_peak_hit_rate = matched_provider_peaks / requested_provider_peaks`, using
  the top 5 provider peaks per side and a match tolerance of two local grid steps

Boundary rules:

- Empty local or provider datasets are Tier 1 failures.
- Zero provider totals are Tier 1 failures, not passing ratios.
- NaN/Infinity MUST NOT be serialized into reports.
- Out-of-range buckets may be retained for audit, but they MUST be excluded from
  score computation only via a named, versioned filter recorded in the report.

## Parity Score

The initial score is a diagnostic gate, not a claim of exact clone behavior.

For the CoinAnK profile, compute:

| Component | Weight |
|-----------|--------|
| Scale alignment | 20 |
| Long/short balance | 20 |
| Grid and bucket density | 15 |
| Normalized shape | 30 |
| Peak alignment | 15 |

Component scoring formulas:

- `scale_score = 20` when `0.5 <= total_scale_ratio <= 2.0`, otherwise `0`.
- `long_short_score = 20` when the local long/short ratio is within `0.6x..1.6x`
  of the provider ratio, otherwise `0`.
- `grid_score = 15` when both `0.5 <= bucket_count_ratio <= 2.0` and
  `0.5 <= price_step_ratio <= 2.0`, otherwise `0`.
- `shape_score = 30 * max(0, normalized_overlap)`, capped to `30`; if
  `pearson_r` is present and negative, cap `shape_score` at `15`.
- `peak_score = 15 * top_peak_hit_rate`, capped to `15`.
- `parity_score = scale_score + long_short_score + grid_score + shape_score + peak_score`.

Tier 1 failures set `parity_score = 0` and must include a machine-readable
`tier1_failure_reason`.

The first accepted CoinAnK profile target is:

- no Tier 1 data/provenance failures
- `parity_score >= 70` on every matrix entry
- `parity_score >= 80` average across the 4-entry matrix
- `total_scale_ratio` within `0.5..2.0`
- `long_short_ratio` within `0.6x..1.6x` of CoinAnK
- `price_step_ratio` within `0.5..2.0`
- `top_peak_hit_rate >= 0.4` using a tolerance of two local grid steps

Coinglass profile acceptance is diagnostic in this spec:

- reports must be generated and comparable
- failures must be explicit
- no product default changes are gated on Coinglass passing

## Functional Requirements

- **FR-001**: The baseline workflow MUST capture and compare Rektslug with
  `surface=public`, not legacy `/liquidations/levels`.
- **FR-002**: Any accepted CoinAnK parity baseline MUST record
  `serving_provenance`; if Binance serves via `legacy-fallback`, the report is
  valid as evidence but not eligible for final artifact-backed signoff.
- **FR-003**: The public endpoint MUST preserve backward compatibility when
  `reference_provider` is omitted.
- **FR-004**: The public endpoint MUST reject unsupported `reference_provider`
  values explicitly.
- **FR-005**: Public responses MUST include parity metadata separate from
  serving provenance metadata.
- **FR-006**: Provider-parity reports MUST persist all metrics listed in the
  Metrics Contract.
- **FR-007**: The CoinAnK profile MUST stop relying on untagged equal-volume
  leverage spreading as evidence of real provider ladder parity. If equal
  spreading remains as a display fallback, it MUST be labeled as display-only in
  model metadata and cannot satisfy final parity signoff.
- **FR-008**: The CoinAnK profile MUST make the long/short ratio a first-class
  calibration target.
- **FR-009**: The CoinAnK profile MUST make the effective price grid step a
  first-class calibration target.
- **FR-010**: The Coinglass profile MUST use the Binance per-exchange `liqMap`
  reference only; aggregate-market and heatmap endpoints are invalid for this
  spec.
- **FR-011**: The workflow MUST keep historical reports readable, including
  older reports that do not contain `reference_provider` or serving-provenance
  fields.
- **FR-012**: Browser validation MUST continue to cover the canonical Binance,
  Bybit, and Hyperliquid public routes after the provider-profile axis is added.

### Acceptance Criteria

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| FR-001 | A baseline run for any matrix entry records `requested_surface=public`, `effective_surface=public`, and `/liquidations/coinank-public-map`; no local `/liquidations/levels` URL appears in the local capture. |
| FR-002 | A CoinAnK parity report includes `serving_provenance`; final signoff rejects reports where Binance serving is `legacy-fallback`. |
| FR-003 | Calling `/liquidations/coinank-public-map` without `reference_provider` returns the same default provider profile as `reference_provider=coinank`. |
| FR-004 | Calling the public endpoint with an unsupported `reference_provider` returns a non-2xx validation error and no partial parity metadata. |
| FR-005 | A public response contains both serving provenance fields and parity metadata fields; tests assert they are distinct values. |
| FR-006 | A generated provider-parity report contains every field listed in the Metrics Contract and no NaN/Infinity values. |
| FR-007 | A report using equal-volume leverage spreading sets a display-only ladder metadata flag and fails final parity signoff. |
| FR-008 | CoinAnK profile reports include local/provider long/short ratios and `long_short_ratio_delta`; the score uses that component. |
| FR-009 | CoinAnK profile reports include local/provider effective price steps and `price_step_ratio`; the score uses that component. |
| FR-010 | A Coinglass profile run rejects aggregate-market and heatmap endpoints and accepts only Binance per-exchange `liqMap`. |
| FR-011 | Existing provider-comparison fixtures without parity metadata still load without exception and are marked `legacy_report=true` or equivalent. |
| FR-012 | Browser regression tests continue passing for Binance, Bybit, and Hyperliquid public routes after the provider-profile axis lands. |

## Non-Functional Requirements

- **NFR-001**: A single public-provider parity comparison for one
  `(symbol, timeframe, reference_provider)` pair SHOULD complete in under 120s
  when local services and provider auth are healthy.
- **NFR-002**: Public API response time SHOULD remain under 2s warm for one
  `(exchange, symbol, timeframe, reference_provider)` request.
- **NFR-003**: The provider-profile axis MUST be deterministic for a fixed
  artifact and calibration config.
- **NFR-004**: Calibration coefficients MUST be versioned and auditable; do not
  silently retune based on the latest provider capture without recording the
  source run.
- **NFR-005**: The implementation MUST not introduce provider-specific logic into
  Hyperliquid public serving.

## Edge Cases

- **EC-001**: CoinAnK and Coinglass disagree for the same matrix entry.
  - Expected: preserve separate profile scores; do not average them into one target.
- **EC-002**: CoinGlass bundle/decode drift breaks the secondary profile.
  - Expected: mark Coinglass diagnostic capture failed; do not block CoinAnK product signoff.
- **EC-003**: Binance public serving falls back to legacy.
  - Expected: report is usable for regression evidence but not final artifact-backed signoff.
- **EC-004**: Bybit artifact exists but Binance parity is not green.
  - Expected: keep Bybit route regression tests green; defer Bybit provider-parity signoff.
- **EC-005**: A calibration improves scale but worsens shape materially.
  - Expected: fail the parity score even if total notional ratio improves.

## Success Criteria

- Public Rektslug vs CoinAnK baseline reports exist for all 4 Binance entries
  with `surface=public` and serving provenance.
- Public Rektslug vs Coinglass diagnostic reports exist or fail explicitly with
  provider/decode errors.
- The public API supports a provider-profile axis without changing the browser
  URL contract.
- The CoinAnK profile reaches the initial parity score gate across
  `BTC/ETH x 1d/1w`.
- Docs clearly state that CoinAnK is the default public reference, Coinglass is
  secondary, and neither is treated as ground truth.
- Heatmap remains explicitly out of scope.
