# Implementation Plan: Scorecard Runtime Evidence Plane

**Branch**: `043-scorecard-runtime-evidence` | **Date**: 2026-05-02 | **Spec**: [spec.md](spec.md)

## Summary

Promote the spec-041/spec-042 scorecard pipeline into a retained runtime evidence
source. Add a reproducible generator, persist latest artifacts, expose
`/ops/scorecard/latest`, add compact `/ops/summary` fields, and emit calibration
metadata for remaining adaptive method values. Keep ownership strictly read-only:
`rektslug` reports expert-quality evidence; `nautilus_dev` owns execution gates.

The implementation MUST comply with the repository `CLAUDE.md` cross-repo rule:
Adaptive Signals, Fixed Safety. Scorecard evidence follows the four pillars;
freshness/fail-closed/governance controls remain explicit safety boundaries.

## Technical Context

**Language/Version**: Python 3.10
**Primary Dependencies**: Existing Pydantic v2, FastAPI, pytest, stdlib only
**Storage**: Local retained JSON artifacts under runtime/data path
**Testing**: pytest + TDD Red-Green-Refactor
**Target Platform**: Docker Compose service and local CLI
**Performance Goal**: Endpoint <500ms, generation <30s for current retained data
**Constraints**: No external ML/statistics dependencies; no execution-side writes
**Scale/Scope**: BTC/ETH, experts `v1`, `v3`, `v4`, `v5`, retained snapshots

## Proposed Runtime Paths

```
data/validation/scorecards/
├── latest.json
├── latest-summary.json
└── runs/
    └── {run_id}/
        ├── scorecard.json
        ├── summary.json
        └── inputs.json
```

In Docker, the API already sees `/app/data:ro`. The generator may write on the
host path; the API reads the retained output.

## Proposed Source Files

```
src/liquidationheatmap/scorecard/runtime.py
src/liquidationheatmap/scorecard/calibration.py
scripts/generate-scorecard-evidence.py
src/liquidationheatmap/api/routers/ops.py
tests/test_scorecard/test_runtime_evidence.py
tests/integration/test_ops_scorecard_endpoint.py
```

## Data Flow

1. Generator loads retained expert snapshots.
2. Generator loads canonical price path and liquidation confirmation data.
3. `ScorecardPipeline.run(..., enable_adaptive=True)` builds the bundle.
4. Runtime layer validates `ExpertScorecardBundle`.
5. Runtime layer writes deterministic JSON artifact and compact summary.
6. `/ops/scorecard/latest` reads and validates latest retained artifact.
7. `/ops/summary` reports compact scorecard health.
8. `nautilus_dev` may consume the endpoint read-only.

## Calibration Metadata Design

Every adaptive value emitted by generation belongs to one of:

- `derived`: output of data distribution or runtime dataset shape
- `method_constant`: computational choice such as bootstrap iteration count
- `governance_constant`: freshness, retention, or fail-closed policy

Example:

```json
{
  "touch_band": {
    "kind": "derived",
    "method": "realized_volatility_bps_to_band",
    "input_count": 1440,
    "selected_values": {"BTCUSDT": 8, "ETHUSDT": 11}
  },
  "bootstrap": {
    "kind": "method_constant",
    "n_bootstrap": 1000,
    "seed_policy": "sha256(slice_key)[:4]"
  },
  "freshness": {
    "kind": "governance_constant",
    "freshness_sla_secs": 86400
  }
}
```

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Mathematical Correctness | PASS | Reuses spec-042 validated primitives |
| TDD | PASS | RED tests required before endpoint/generator code |
| Data Integrity | PASS | Schema validation before healthy status |
| Graceful Degradation | PASS | Explicit unavailable/degraded/blocked semantics |
| Progressive Enhancement | PASS | Adds endpoint; does not break existing scorecard API |
| Ownership Boundary | PASS | Read-only provider; no execution controls |
| Four Pillars | PASS | Probabilistic, non-linear, non-parametric, scalable evidence only |
| Fixed Safety | PASS | Governance constants are labeled, not made adaptive |

No violations.

## Risk Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Missing price-path source | No scorecard evidence | Fail closed with `UNAVAILABLE` |
| Partial retained snapshots | False confidence | Emit coverage gaps and degrade |
| Artifact too large for summary | Slow cockpit | Summary returns compact headline fields |
| Hidden method constants remain | Non-parametric drift | Emit calibration metadata with category labels |
| Generator corrupts latest file | Bad provider state | Write temp file then atomic rename |
| Docker API lacks artifact mount | Endpoint unavailable | Add compose/deploy test for `/app/data` visibility |

## Phase Breakdown

### Phase 1: Contracts and Test Scaffolding

Create test files and source file stubs (empty modules). No implementation yet.

### Phase 2: Runtime Evidence Models

RED tests for models/contracts, then implement summary and calibration helpers.

### Phase 3: Artifact Writer

Deterministic JSON writer with atomic temp-file rename and reproducibility hash.

### Phase 4: Generator CLI

`scripts/generate-scorecard-evidence.py` — runs adaptive pipeline, validates
output, writes retained artifacts, exits non-zero on blocking gaps.

### Phase 5: Ops Endpoint

`GET /ops/scorecard/latest` with fail-closed semantics.

### Phase 6: Summary Integration

Wire compact scorecard fields into `GET /ops/summary`.

### Phase 7: Data Quality Status

Implement quality classifier: HEALTHY/DEGRADED/BLOCKED/UNAVAILABLE transitions.

### Phase 8: Calibration Metadata

Expose derived/method_constant/governance_constant labels in artifact.
Do not hide constants in code without metadata.

### Phase 9: Docker and Deploy Guardrails

Ensure API container can read retained scorecard artifacts. Verify
`data/validation/scorecards/` is covered by existing `/app/data` volume mount.

### Phase 10: Documentation and Cross-Repo Smoke

Update docs, run targeted tests, cross-repo smoke with `nautilus_dev` cockpit.
Verify provider integration can see scorecard status while final readiness
remains owned by `nautilus_dev`.

## Ownership

| Capability | Owner |
|-----------|-------|
| Scorecard evidence artifact | `rektslug` |
| Scorecard endpoint | `rektslug` |
| Calibration metadata | `rektslug` |
| Signal/expert-quality status | `rektslug` |
| Execution readiness | `nautilus_dev` |
| Operator controls | `nautilus_dev` |
| Risk controls | `nautilus_dev` |

## Resolved Implementation Decisions

1. **Freshness SLA default**: `86400` seconds (24h), governance constant (spec.md Parameter Policy).
2. **Generator schedule**: Manual CLI only for first release; scheduled sidecar deferred (spec.md Foundational Rule 7).
3. **Price-path source**: Retained price-path files from signal pipeline under `data/validation/` (spec.md Foundational Rule 6).
