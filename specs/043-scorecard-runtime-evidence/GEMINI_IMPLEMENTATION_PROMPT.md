# YOLO Implementation Prompt: spec-043 Scorecard Runtime Evidence Plane

**Branch**: `043-scorecard-runtime-evidence`
**Mode**: YOLO — implement all phases autonomously, commit per phase, no questions.
**Runner**: `uv run pytest` for all tests. `uv run ruff check . && uv run ruff format .` before each commit.

---

## MISSION

Implement the scorecard runtime evidence plane for `rektslug`. This adds:
1. A deterministic artifact writer that persists scorecard bundles as JSON
2. A CLI generator script
3. `GET /ops/scorecard/latest` endpoint
4. Scorecard status in `GET /ops/summary`
5. Data quality classifier (HEALTHY/DEGRADED/BLOCKED/UNAVAILABLE)
6. Calibration metadata with labeled parameter categories

You MUST follow TDD Red-Green-Refactor. You MUST commit after each phase.

---

## CRITICAL RULES

1. **Import style**: Always `from src.liquidationheatmap...` (NOT `from liquidationheatmap...`)
2. **Python version**: 3.10 compatible (no `datetime.UTC`, use `datetime.timezone.utc`; no `StrEnum`)
3. **No new dependencies**: Only stdlib + existing deps (pydantic v2, fastapi, pytest). NO numpy, scipy, pandas, sklearn.
4. **Deterministic JSON**: Use `json.dumps(obj, sort_keys=True, default=str)` for reproducibility
5. **Atomic writes**: Write to temp file, then `os.replace()` (atomic on POSIX)
6. **Fail closed**: Never write green artifact when inputs missing or schema validation fails
7. **Read-only endpoint**: The endpoint reads files, never mutates state
8. **No fabrication**: Never return zero counters, placeholder probabilities, or fake artifact links
9. **Freshness SLA**: `86400` seconds (governance constant, not adaptive)

---

## EXISTING CODEBASE CONTEXT

### ExpertScorecardBundle (src/liquidationheatmap/models/scorecard.py:199)
```python
class ExpertScorecardBundle(BaseModel):
    slices: List[ExpertScorecardSlice]
    coverage_gaps: Optional[Dict[str, Any]] = None
    dominance_rows: Optional[List[Dict[str, Any]]] = None
    retained_input_range: Optional[Dict[str, Any]] = None
    artifact_provenance: Optional[Dict[str, Any]] = None
    adaptive_parameters: Optional[Dict[str, Any]] = None
```

### ScorecardPipeline (src/liquidationheatmap/scorecard/pipeline.py)
- Already has `run_from_retained_snapshots(price_path, liquidation_events, expected_experts, symbols, limit_manifests, enable_adaptive)` returning JSON string
- Already has `run(artifacts, price_path, liquidation_events, expected_experts, enable_adaptive)` returning JSON string
- Already has `load_retained_artifacts(symbols, expert_ids, limit_manifests)` returning list of dicts
- Constructor: `ScorecardPipeline(snapshot_root=DEFAULT_SNAPSHOT_ROOT)`
- `DEFAULT_SNAPSHOT_ROOT = Path("data/validation/expert_snapshots/hyperliquid")`

### OpsEnvelope (src/liquidationheatmap/api/routers/ops.py:121)
```python
class OpsEnvelope(BaseModel):
    provider_id: str = "rektslug"
    schema_version: str = "1.0.0"
    generated_at: str = Field(default_factory=_utc_now)
    status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
    freshness_sla_secs: int = 60
    last_error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
```

### Existing ops.py endpoints
- `GET /ops/summary` — returns OpsEnvelope with details dict containing redis, signals, shadow, etc.
- `GET /ops/shadow-report`
- `GET /ops/continuous-report`
- `GET /ops/evidence/spec-040/latest`
- `GET /ops/backfill-status`
- Helper: `_repo_root()` returns project root Path
- Helper: `_utc_now()` returns ISO UTC string

### Existing scorecard package (src/liquidationheatmap/scorecard/)
- `__init__.py` — re-exports ScorecardPipeline, ScorecardBuilder, etc.
- `pipeline.py` (524 LOC) — end-to-end bundle generation
- `builder.py` (402 LOC) — observation extraction, touch detection
- `adaptive.py` (262 LOC) — adaptive touch band, quantile buckets, volume threshold, regime inference
- `bootstrap.py` (94 LOC) — bootstrap dominance comparison
- `slicer.py` (121 LOC) — slice creation
- `aggregator.py` (87 LOC) — aggregation

### Adaptive functions available (src/liquidationheatmap/scorecard/adaptive.py)
- `compute_adaptive_touch_band(observations, base_bps, min_obs)` → int
- `compute_volume_threshold(observations, quantile)` → float
- `compute_quantile_buckets(distances, n_buckets, min_obs_per_bucket)` → QuantileBucketSet
- `infer_regime_map(observations, symbols)` → dict
- `compute_realized_volatility(prices, window)` → float

### Runtime paths
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

---

## NEW FILES TO CREATE

1. `src/liquidationheatmap/scorecard/runtime.py` — evidence summary, quality classifier, artifact writer
2. `src/liquidationheatmap/scorecard/calibration.py` — calibration metadata extraction and labeling
3. `scripts/generate-scorecard-evidence.py` — CLI entry point
4. `tests/test_scorecard/test_runtime_evidence.py` — unit tests
5. `tests/integration/test_ops_scorecard_endpoint.py` — integration tests

### Files to modify
6. `src/liquidationheatmap/api/routers/ops.py` — add `/ops/scorecard/latest`, wire summary fields
7. `src/liquidationheatmap/scorecard/__init__.py` — re-export new modules

---

## DATA MODEL (implement as Pydantic v2)

### ScorecardEvidenceEnvelope
```
provider_id: str = "rektslug"
schema_version: str = "1.0.0"
generated_at: datetime
status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
freshness_sla_secs: int = 86400
last_error: str | None
details: ScorecardEvidenceDetails | ScorecardErrorDetails
```

### ScorecardEvidenceDetails (healthy/degraded response)
```
artifact_path: str
summary_path: str
artifact_generated_at: datetime
artifact_age_secs: int
adaptive_mode: bool
experts: list[str]
symbols: list[str]
slice_count: int
observation_count: int
dominance_row_count: int
coverage_gap_count: int
blocking_issues: list[str]
quality: ScorecardQualitySummary
calibration_metadata: dict[str, CalibrationMetadataEntry]
artifact_links: dict[str, str]
```

### ScorecardErrorDetails (unavailable/blocked response)
```
blocking_issues: list[str]
```

### ScorecardQualitySummary
```
snapshot_coverage_status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
price_path_coverage_status: Literal[...]
volume_coverage_status: Literal[...]
liquidation_confirmation_status: Literal[...]
schema_validation_status: Literal[...]
reproducibility_hash: str
```

### CalibrationMetadataEntry
```
kind: Literal["derived", "method_constant", "governance_constant"]
name: str
value: Any
method: str
input_count: int | None = None
reason: str
```

---

## ENDPOINT CONTRACT

### GET /ops/scorecard/latest

**Happy path (200)**:
```json
{
  "provider_id": "rektslug",
  "schema_version": "1.0.0",
  "generated_at": "2026-05-02T16:00:00Z",
  "status": "HEALTHY",
  "freshness_sla_secs": 86400,
  "last_error": null,
  "details": {
    "artifact_path": "data/validation/scorecards/latest.json",
    "summary_path": "data/validation/scorecards/latest-summary.json",
    "artifact_generated_at": "2026-05-02T15:55:00Z",
    "artifact_age_secs": 300,
    "adaptive_mode": true,
    "experts": ["v1", "v3", "v4", "v5"],
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "slice_count": 120,
    "observation_count": 4800,
    "dominance_row_count": 360,
    "coverage_gap_count": 0,
    "blocking_issues": [],
    "quality": { ... },
    "calibration_metadata": { ... },
    "artifact_links": { ... }
  }
}
```

**Missing artifact (503)**:
```json
{
  "provider_id": "rektslug",
  "status": "UNAVAILABLE",
  "freshness_sla_secs": 86400,
  "last_error": "scorecard artifact missing",
  "details": { "blocking_issues": ["scorecard artifact missing"] }
}
```

### GET /ops/summary additions
Add to existing details dict:
```json
{
  "scorecard_status": "HEALTHY",
  "scorecard_summary": {
    "artifact_generated_at": "...",
    "adaptive_mode": true,
    "experts": ["v1", "v3", "v4", "v5"],
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "observation_count": 4800,
    "slice_count": 120,
    "coverage_gap_count": 0
  }
}
```

---

## TASKS (execute in order, commit per phase)

### Phase 1: Contracts and Test Scaffolding
- T001: Create `tests/test_scorecard/test_runtime_evidence.py` (empty test module with imports)
- T002: Create `tests/integration/test_ops_scorecard_endpoint.py` (empty test module)
- T003: Create `src/liquidationheatmap/scorecard/runtime.py` (empty module stub)
- T004: Create `src/liquidationheatmap/scorecard/calibration.py` (empty module stub)
- T005: Create `scripts/generate-scorecard-evidence.py` (argparse skeleton only)

**Commit**: `feat(scorecard): scaffold runtime evidence files (Phase 1)`

### Phase 2: Runtime Evidence Models
- T006: RED: write model/contract tests for ScorecardEvidenceDetails, ScorecardQualitySummary, CalibrationMetadataEntry
- T007: Implement models and summary helpers in runtime.py
- T008: Implement calibration metadata helpers in calibration.py
- T008b: RED: write test that ExpertScorecardBundle from spec-041/042 loads in new runtime layer
- T009: GREEN: all model tests pass

**Commit**: `feat(scorecard): implement runtime evidence models (Phase 2)`

### Phase 3: Artifact Writer
- T010: RED: write failing test that valid ExpertScorecardBundle writes latest.json and latest-summary.json
- T011: RED: write failing reproducibility test (same inputs → byte-identical JSON)
- T012: Implement deterministic canonical JSON writer with atomic temp-file rename
- T013: Implement reproducibility hash (sha256 of canonical JSON)
- T014: GREEN: artifact writer tests pass

**Commit**: `feat(scorecard): deterministic artifact writer (Phase 3)`

### Phase 4: Generator CLI
- T015: RED: write failing CLI test for successful adaptive evidence generation
- T016: RED: write failing CLI test that missing snapshots exits non-zero, no green artifact
- T017: Implement scripts/generate-scorecard-evidence.py
- T018: Wire ScorecardPipeline.run_from_retained_snapshots into generator
- T019: Persist input provenance and generation command metadata
- T020: GREEN: generator tests pass

**Commit**: `feat(scorecard): generator CLI script (Phase 4)`

### Phase 5: Ops Endpoint
- T021: RED: failing integration test GET /ops/scorecard/latest → HEALTHY from valid artifact
- T022: RED: failing integration test missing artifact → 503 UNAVAILABLE
- T023: RED: failing integration test invalid schema → fail-closed
- T024: Add /ops/scorecard/latest route in ops.py
- T025: Validate artifact against ExpertScorecardBundle before healthy
- T026: GREEN: endpoint tests pass
- T026b: RED: test POST/PUT/DELETE → 405

**Commit**: `feat(scorecard): ops scorecard endpoint (Phase 5)`

### Phase 6: Summary Integration
- T027: RED: failing test /ops/summary includes scorecard_status
- T028: RED: failing test /ops/summary includes compact scorecard_summary
- T029: Wire scorecard status into /ops/summary
- T030: Assert /ops/summary does NOT contain full bundle fields (calibration_metadata, artifact_links excluded)
- T031: GREEN: summary tests pass

**Commit**: `feat(scorecard): wire scorecard into ops summary (Phase 6)`

### Phase 7: Data Quality Status
- T032: RED: stale artifact → DEGRADED
- T033: RED: coverage gaps → DEGRADED
- T034: RED: blocking schema issue → BLOCKED
- T035: Implement quality classifier
- T036: Emit blocking issues and coverage gap count
- T037: GREEN: quality tests pass

**Commit**: `feat(scorecard): data quality classifier (Phase 7)`

### Phase 8: Calibration Metadata
- T038: RED: calibration metadata labels derived values
- T039: RED: bootstrap settings labeled method_constant
- T040: RED: freshness SLA labeled governance_constant
- T041: Implement calibration metadata extraction
- T042: Implement method/governance constant labels
- T043: GREEN: calibration tests pass

**Commit**: `feat(scorecard): calibration metadata labels (Phase 8)`

### Phase 9: Docker and Deploy Guardrails
- T044: RED: test docker-compose.yml volume config covers scorecard path
- T045: Update docker-compose.yml if needed
- T046: GREEN: compose test passes

**Commit**: `fix(deploy): ensure scorecard artifact mount (Phase 9)`

### Phase 10: Documentation and Cross-Repo Smoke
- T047: Update docs/ARCHITECTURE.md with scorecard evidence endpoint
- T048: Add quickstart reference
- T048b-d: Verify NFR benchmarks (latency <500ms, generation <30s, no new ML deps)
- T049: Run full targeted test suite
- T050: Skip cross-repo smoke (nautilus_dev not in this repo)
- T051: Record final status

**Commit**: `docs(scorecard): runtime evidence documentation (Phase 10)`

---

## QUALITY GATES (check before EACH commit)

```bash
uv run ruff check . && uv run ruff format .
uv run pytest tests/test_scorecard/ tests/integration/test_ops_scorecard_endpoint.py -v
```

All tests MUST be green before committing. If a test fails, fix it before moving to the next phase.

---

## ANTI-PATTERNS (DO NOT)

- Do NOT add numpy, scipy, pandas, or any ML library
- Do NOT use `from liquidationheatmap...` (use `from src.liquidationheatmap...`)
- Do NOT modify ExpertScorecardBundle model — it's spec-041/042 contract
- Do NOT add POST/PUT/DELETE endpoints
- Do NOT hardcode test data that masks real failures
- Do NOT skip TDD — every implementation MUST have a RED test first
- Do NOT create a green artifact when inputs are missing
- Do NOT embed full scorecard bundle in /ops/summary response
- Do NOT use datetime.UTC (Python 3.10 compat — use datetime.timezone.utc)
- Do NOT use StrEnum (Python 3.10 compat — use Literal[] instead)
- Do NOT amend commits — create new commits per phase

---

## REFERENCE ARTIFACTS

Read these files in the repo before starting:
- `specs/043-scorecard-runtime-evidence/spec.md` — full spec
- `specs/043-scorecard-runtime-evidence/plan.md` — implementation plan
- `specs/043-scorecard-runtime-evidence/data-model.md` — Pydantic contracts
- `specs/043-scorecard-runtime-evidence/contracts/ops-scorecard-latest.md` — endpoint contract
- `specs/043-scorecard-runtime-evidence/quickstart.md` — CLI usage
- `src/liquidationheatmap/scorecard/pipeline.py` — existing pipeline (reuse, don't rewrite)
- `src/liquidationheatmap/models/scorecard.py` — existing models (don't modify)
- `src/liquidationheatmap/api/routers/ops.py` — existing ops router (extend)

---

## GO

Start with Phase 1. Commit after each phase. Do not ask questions. If something is ambiguous, make the simplest KISS choice and document it in the commit message.
