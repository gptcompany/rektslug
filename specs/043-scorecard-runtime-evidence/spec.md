# Feature Specification: Scorecard Runtime Evidence Plane

**Feature Branch**: `043-scorecard-runtime-evidence`
**Created**: 2026-05-02
**Status**: Draft
**Input**: Promote spec-041/spec-042 expert scorecard from offline library output to retained runtime evidence
**Dependencies**: spec-041, spec-042, spec-040 ops endpoints
**Pillar Alignment**: Probabilistico, Non Lineare, Non Parametrico, Scalare
**Governance Source**: Repository `CLAUDE.md` section "Adaptive Signals, Fixed Safety"

## Context

spec-041 introduced empirical expert scorecards for Hyperliquid experts `v1`, `v3`,
`v4`, and `v5`. spec-042 replaced fixed observation-layer thresholds with
data-derived adaptive primitives. The implementation is now useful as a research
pipeline, but it is not yet a first-class runtime evidence source.

Today the operator can see that `rektslug` is healthy and that signals are flowing,
but cannot query a canonical retained scorecard artifact through `/ops`. The
adaptive layer also still has method constants such as lookback ticks, bucket caps,
bootstrap iterations, and sample floors. These are not trading parameters, but
they must be visible, justified, and preferably self-calibrated where possible.

This spec creates a small runtime evidence plane for scorecards:

- generate retained adaptive scorecard bundles on a schedule or CLI command
- persist the latest valid artifact with provenance and data-quality metadata
- expose read-only `/ops/scorecard/latest` and summary fields
- distinguish process health from scorecard evidence quality
- reduce non-safety method parameters by deriving them from observed data

## Four-Pillar Compliance

This feature MUST follow the cross-repo `nautilus_dev` pillars now documented in
repository `CLAUDE.md`.

| Pillar | Requirement in this spec |
|--------|--------------------------|
| Probabilistico | Scorecard evidence emits probabilities, quantiles, bootstrap confidence intervals, sample counts, and uncertainty flags; no mandatory global score |
| Non Lineare | Slicing and dominance use quantiles, distributions, and regime-conditioned comparisons instead of linear fixed grids |
| Non Parametrico | Signal/evidence method values are derived from observed data where possible; remaining method constants are exposed in calibration metadata |
| Scalare | Evidence uses bps, ratios, volume clocks, quantile partitions, and symbol-normalized metadata so BTC/ETH and future symbols share the same contract |

Safety/governance controls are explicitly outside the adaptive scope and remain
fixed or owned by `nautilus_dev`.

## Foundational Rules

1. `rektslug` owns signal and expert-quality evidence only. It MUST NOT own
   execution readiness, risk controls, operator controls, or live-trading gates.
2. Runtime scorecard evidence MUST be real retained output. It MUST NOT fabricate
   zero counters, placeholder probabilities, or synthetic artifact links.
3. If a method value can be derived from retained data shape, liquidity, sample
   size, or runtime cost, it SHOULD be computed and emitted as metadata instead of
   hardcoded silently.
4. Safety/governance limits are not alpha parameters. Freshness SLAs, fail-closed
   behavior, circuit breakers, and retention bounds MAY remain explicit constants,
   but MUST be labeled as governance controls.
5. The scorecard is probabilistic evidence, not a trading decision. It MAY inform
   `nautilus_dev`; it MUST NOT place orders or change execution state.
6. The generator MUST use the retained price-path files already produced by the
   signal pipeline (under `data/validation/`). If no retained price path exists,
   the generator MUST fail closed with `UNAVAILABLE`. QuestDB and DuckDB exports
   are future alternatives and out of scope for this spec.
7. First release uses manual CLI invocation only. Scheduled generation
   (cron/systemd/docker sidecar) is deferred to a follow-up spec.

## Scope

### In Scope

- Persist latest scorecard bundle generated from retained expert snapshots.
- Add read-only endpoint `GET /ops/scorecard/latest`.
- Add summary fields to `GET /ops/summary`.
- Add runtime CLI/script for generating scorecard evidence.
- Add artifact retention and provenance metadata.
- Add scorecard quality classification: `HEALTHY`, `DEGRADED`, `BLOCKED`,
  `UNAVAILABLE`.
- Add data-quality metadata for snapshot coverage, price-path coverage, volume
  availability, liquidation-confirmation coverage, and bootstrap completeness.
- Replace or expose remaining non-safety method constants as computed
  `calibration_metadata`.
- Keep spec-041 non-adaptive compatibility and spec-042 adaptive mode.

### Out of Scope

- `nautilus_dev` operator controls, risk controls, or final paper/live readiness.
- Mainnet promotion policy.
- New browser UI in `rektslug`.
- ML classifiers, neural models, or parametric fitting.
- Automatic expert selection for execution.
- Changing signal generation logic.
- Writing to `nautilus_dev` runtime artifacts.

## User Scenarios & Testing

### User Story 1 - Retained Scorecard Evidence Endpoint (Priority: P1)

As an operator, I need one canonical endpoint for the latest retained expert
scorecard so that the cockpit and scripts can validate expert-quality evidence
without parsing local files.

**Independent Test**: Generate a scorecard artifact, then query
`GET /ops/scorecard/latest` and verify that the response is `HEALTHY`, includes
the retained artifact path, and contains real scorecard summary metrics.

**Acceptance Scenarios**:

1. **Given** a valid retained scorecard artifact exists, **When**
   `/ops/scorecard/latest` is requested, **Then** it returns `200` with
   `status=HEALTHY` and a real payload summary.
2. **Given** no scorecard artifact exists, **When** the endpoint is requested,
   **Then** it returns `503` with `status=UNAVAILABLE`.
3. **Given** an artifact exists but fails schema validation, **When** the endpoint
   is requested, **Then** it returns `503` or `200 BLOCKED` according to the
   fail-closed contract and includes a blocking issue.
4. **Given** an artifact is stale, **When** the endpoint is requested, **Then**
   the status is `DEGRADED` and the age is exposed.

---

### User Story 2 - Runtime Generation and Retention (Priority: P1)

As an operator, I need a reproducible command/job that generates the scorecard
artifact from retained expert snapshots so that scorecard evidence can be refreshed
without manual notebook work.

**Independent Test**: Run the generation command twice with the same inputs and
verify byte-identical scorecard JSON and stable retained artifact metadata.

**Acceptance Scenarios**:

1. **Given** retained expert snapshots and price paths exist, **When** the
   generator runs, **Then** it writes a JSON bundle and summary artifact under a
   deterministic runtime path.
2. **Given** the same inputs are used twice, **When** the generator runs twice,
   **Then** the machine-readable output is reproducible.
3. **Given** required inputs are missing, **When** the generator runs, **Then** it
   fails closed and writes no misleading green artifact.
4. **Given** partial inputs exist, **When** generation completes, **Then** coverage
   gaps are persisted and status is not silently green.

---

### User Story 3 - Self-Calibrating Method Metadata (Priority: P1)

As a researcher, I need remaining adaptive method choices to be derived or exposed
so that scorecard results are auditable and not hidden behind unexplained constants.

**Independent Test**: Run scorecard generation on two datasets with different
sample sizes and liquidity profiles. Verify that calibration metadata differs and
is included in the artifact.

**Acceptance Scenarios**:

1. **Given** sufficient retained observations, **When** bucket counts are computed,
   **Then** the number of buckets is derived from sample size and minimum viable
   observations per bucket.
2. **Given** different volume profiles, **When** volume-clock thresholds are
   computed, **Then** the artifact emits the observed volume distribution and the
   selected threshold.
3. **Given** bootstrap comparisons are run, **When** runtime cost is measured,
   **Then** the artifact emits `n_bootstrap`, seed policy, and comparison count.
4. **Given** a method constant remains explicit, **When** the artifact is emitted,
   **Then** it is labeled as `method_constant` or `governance_constant`.

---

### User Story 4 - Data Quality and Evidence Health (Priority: P1)

As an operator, I need scorecard health to reflect data quality, not just process
availability, so that stale or partial evidence does not look production-ready.

**Independent Test**: Run endpoint tests with fresh, stale, partial, and invalid
artifacts and verify the status transitions.

**Acceptance Scenarios**:

1. **Given** snapshot coverage is complete and artifact is fresh, **When** summary
   is requested, **Then** `scorecard_status=HEALTHY`.
2. **Given** artifact exists but price-path coverage is partial, **When** summary
   is requested, **Then** `scorecard_status=DEGRADED`.
3. **Given** required schema fields are missing, **When** summary is requested,
   **Then** `scorecard_status=BLOCKED`.
4. **Given** no latest artifact exists, **When** summary is requested, **Then**
   `scorecard_status=UNAVAILABLE`.

---

### User Story 5 - Cockpit Provider Compatibility (Priority: P2)

As the `nautilus_dev` cockpit aggregator, I need a small stable read-only payload
so that scorecard evidence can be displayed without embedding `rektslug` internals.

**Independent Test**: Query `/ops/summary` and `/ops/scorecard/latest`; verify that
summary contains only health and headline metrics, while the dedicated endpoint
contains detailed evidence.

**Acceptance Scenarios**:

1. **Given** scorecard evidence is healthy, **When** `/ops/summary` is requested,
   **Then** it includes `scorecard_status=HEALTHY` and a compact summary.
2. **Given** scorecard evidence is unavailable, **When** `/ops/summary` is
   requested, **Then** provider health may degrade but execution readiness remains
   owned by `nautilus_dev`.
3. **Given** the cockpit requests details, **When** it calls
   `/ops/scorecard/latest`, **Then** it receives artifact links and quality
   metadata without any control-plane fields.

## Functional Requirements

- **FR-001**: The system MUST persist the latest scorecard evidence artifact under
  a canonical runtime path.
- **FR-002**: The system MUST expose `GET /ops/scorecard/latest`.
- **FR-003**: The endpoint MUST return a provider envelope with `provider_id`,
  `schema_version`, `generated_at`, `status`, `freshness_sla_secs`, `last_error`,
  and `details`.
- **FR-004**: The endpoint MUST validate the retained artifact against the
  `ExpertScorecardBundle` schema before reporting it healthy.
- **FR-005**: The endpoint MUST fail closed when no real artifact exists.
- **FR-006**: The endpoint MUST distinguish `UNAVAILABLE`, `DEGRADED`, `BLOCKED`,
  and `HEALTHY`.
- **FR-007**: `/ops/summary` MUST include `scorecard_status` and a compact
  `scorecard_summary`.
- **FR-008**: The scorecard summary MUST include at least: artifact timestamp,
  artifact path, expert IDs, symbols, slice count, observation count, coverage gap
  count, dominance row count, adaptive mode, and quality status.
- **FR-009**: The retained artifact MUST include provenance for snapshot root,
  price-path source, liquidation-confirmation source, generation command, and input
  time range.
- **FR-010**: The retained artifact MUST include data-quality metadata for snapshot
  coverage, price-path coverage, volume availability, and liquidation confirmation
  availability.
- **FR-011**: The retained artifact MUST include calibration metadata for remaining
  method values used by adaptive scoring.
- **FR-012**: Calibration metadata MUST label values as `derived`,
  `method_constant`, or `governance_constant`.
- **FR-013**: The generator MUST be reproducible for identical inputs.
- **FR-014**: The generator MUST not write a green artifact when required inputs are
  missing or schema validation fails.
- **FR-015**: The endpoint MUST not fabricate zero probabilities, zero counters, or
  placeholder artifact links.
- **FR-016**: The system MUST preserve spec-041/spec-042 bundle compatibility.
- **FR-017**: The endpoint MUST be read-only and MUST NOT mutate execution state.
- **FR-018**: The implementation MUST include TDD RED tests for each endpoint and
  generator behavior before production code.

## Non-Functional Requirements

- **NFR-001**: Endpoint response time SHOULD be below 500ms when reading a local
  retained artifact.
- **NFR-002**: Scorecard generation SHOULD complete in under 30 seconds for current
  BTC/ETH retained datasets.
- **NFR-003**: JSON output MUST be deterministic for identical inputs.
- **NFR-004**: Runtime endpoint failures MUST be observable via `last_error` and
  `blocking_issues`.
- **NFR-005**: The endpoint MUST avoid returning the full scorecard bundle in
  `/ops/summary`; detailed payload belongs in `/ops/scorecard/latest`.
- **NFR-006**: The implementation MUST not introduce external ML/statistics
  dependencies for this feature.

## Status Semantics

| Status | Meaning |
|--------|---------|
| `HEALTHY` | Latest artifact exists, is fresh, schema-valid, and has no blocking quality gaps |
| `DEGRADED` | Artifact exists and is schema-valid, but stale or partially covered |
| `BLOCKED` | Artifact exists but fails a hard contract or contains blocking quality issues |
| `UNAVAILABLE` | No usable retained scorecard artifact exists |

## Parameter Policy

| Category | Policy |
|----------|--------|
| Market thresholds | SHOULD be derived from observed data |
| Method constants | MAY remain, but MUST be emitted in calibration metadata |
| Governance constants | MAY remain explicit and MUST be labeled |
| Freshness SLA | Governance constant, default `86400` seconds (24h). Adjustable per-deployment but not adaptive. |
| Execution limits | Out of scope; owned by `nautilus_dev` |

## Success Criteria

- **SC-001**: `GET /ops/scorecard/latest` returns `HEALTHY` with real retained
  evidence after generation.
- **SC-002**: `GET /ops/summary` exposes coherent `scorecard_status`.
- **SC-003**: Same inputs generate byte-identical JSON artifacts.
- **SC-004**: Missing or invalid artifacts never produce green status.
- **SC-005**: Calibration metadata identifies every remaining adaptive method value.
- **SC-006**: Cross-repo cockpit can consume scorecard status without direct file
  parsing.

## Open Questions

None. All questions resolved in Foundational Rules and Parameter Policy.
