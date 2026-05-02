# External Review Prompt: spec-043 Scorecard Runtime Evidence Plane

**Branch**: `043-scorecard-runtime-evidence`
**Role**: Post-implementation reviewer (Claude)
**Prerequisite**: Gemini has completed all 10 phases per `GEMINI_IMPLEMENTATION_PROMPT.md`
**Base commit** (pre-implementation): `c34c6bd`

---

## MISSION

Review the Gemini implementation of spec-043. Verify correctness, contract compliance, test quality, and adherence to project conventions. Fix any issues found. Do NOT rewrite working code — only fix real problems.

---

## REVIEW PROTOCOL

Execute each step sequentially. Do not skip steps. Report findings as you go.

### Step 1: Commit Inventory

```bash
git log --oneline c34c6bd..HEAD
```

Verify there are ~10 commits (one per phase). List them with a one-line summary. Flag any missing phases.

### Step 2: Test Suite Health

```bash
uv run pytest tests/test_scorecard/ tests/integration/test_ops_scorecard_endpoint.py -v --tb=short
```

All tests MUST pass. Count: total tests, passed, failed, skipped. If any fail, investigate and fix before continuing.

### Step 3: Full Suite Regression

```bash
uv run pytest --tb=short -q
```

Verify no existing tests were broken. If failures exist, determine if they are pre-existing or introduced by spec-043.

### Step 4: Lint Check

```bash
uv run ruff check . && uv run ruff format --check .
```

Fix any lint or format issues.

### Step 5: Import Style Audit

```bash
grep -rn "from liquidationheatmap\." \
  src/liquidationheatmap/scorecard/runtime.py \
  src/liquidationheatmap/scorecard/calibration.py \
  scripts/generate-scorecard-evidence.py \
  tests/test_scorecard/test_runtime_evidence.py \
  tests/integration/test_ops_scorecard_endpoint.py 2>/dev/null
```

MUST be zero results. All imports must use `from src.liquidationheatmap...` pattern.

### Step 6: Python 3.10 Compatibility

```bash
grep -rn "datetime\.UTC\|StrEnum" \
  src/liquidationheatmap/scorecard/runtime.py \
  src/liquidationheatmap/scorecard/calibration.py \
  scripts/generate-scorecard-evidence.py 2>/dev/null
```

MUST be zero results. Verify `datetime.timezone.utc` and `Literal[]` are used instead.

### Step 7: Contract Compliance

Read these files and verify the implementation matches:

1. **Data model** (`specs/043-scorecard-runtime-evidence/data-model.md`):
   - ScorecardEvidenceEnvelope fields present and typed correctly
   - ScorecardEvidenceDetails fields present
   - ScorecardQualitySummary fields present
   - CalibrationMetadataEntry has `kind`, `name`, `value`, `method`, `input_count`, `reason`
   - Error envelope (UNAVAILABLE/BLOCKED) uses reduced details with only `blocking_issues`

2. **Endpoint contract** (`specs/043-scorecard-runtime-evidence/contracts/ops-scorecard-latest.md`):
   - 200 response matches healthy contract shape
   - 503 response matches missing-artifact contract shape
   - `/ops/summary` includes `scorecard_status` and `scorecard_summary`
   - Summary does NOT contain full bundle fields (calibration_metadata, artifact_links)

3. **Spec foundational rules** (`specs/043-scorecard-runtime-evidence/spec.md`):
   - Rule 1: rektslug owns signal/evidence only, NOT execution
   - Rule 2: No fabricated data (zero counters, placeholder links)
   - Rule 3: Method values derived or emitted as metadata
   - Rule 4: Governance constants labeled
   - Rule 5: Read-only, no orders
   - Rule 6: Price-path from retained files under `data/validation/`
   - Rule 7: Manual CLI only (no scheduler)

### Step 8: Functional Requirements Coverage

Verify each FR has implementation AND test:

| FR | Description | Check |
|----|-------------|-------|
| FR-001 | Persist latest artifact | Writer creates `latest.json` |
| FR-002 | GET /ops/scorecard/latest | Route exists in ops.py |
| FR-003 | Provider envelope fields | Response has provider_id, schema_version, generated_at, status, freshness_sla_secs, last_error, details |
| FR-004 | Schema validation before healthy | ExpertScorecardBundle.model_validate called |
| FR-005 | Fail closed when no artifact | Returns 503/UNAVAILABLE |
| FR-006 | Status semantics (4 states) | HEALTHY/DEGRADED/BLOCKED/UNAVAILABLE logic |
| FR-007 | Summary includes scorecard_status | /ops/summary wired |
| FR-008 | Summary contents (8+ fields) | artifact_generated_at, artifact_path, experts, symbols, slice_count, observation_count, coverage_gap_count, dominance_row_count, adaptive_mode, quality status |
| FR-009 | Provenance metadata | snapshot_root, price_path_source, command, time_range |
| FR-010 | Data quality metadata | snapshot/price_path/volume/liq_confirm coverage statuses |
| FR-011 | Calibration metadata present | calibration_metadata dict in artifact |
| FR-012 | Value labels (derived/method/governance) | kind field in each entry |
| FR-013 | Reproducibility | Same inputs → byte-identical JSON |
| FR-014 | No green on bad input | Missing inputs → no artifact written |
| FR-015 | No fabrication | No zero counters or placeholder links |
| FR-016 | Backward compat spec-041/042 | ExpertScorecardBundle from existing pipeline loads in runtime |
| FR-017 | Read-only endpoint | POST/PUT/DELETE → 405 |
| FR-018 | TDD RED tests first | Test commits precede impl commits |

### Step 9: Non-Functional Requirements

| NFR | Check |
|-----|-------|
| NFR-001 | Endpoint reads local file — inherently <500ms |
| NFR-002 | Generator uses existing pipeline — verify no O(n²) additions |
| NFR-003 | JSON determinism — sort_keys=True, stable serialization |
| NFR-004 | Errors observable — last_error and blocking_issues populated |
| NFR-005 | Summary compact — no full bundle embedded |
| NFR-006 | No new ML deps — check pyproject.toml diff |

```bash
git diff c34c6bd..HEAD -- pyproject.toml | grep "^+" | grep -v "^+++"
```

### Step 10: ExpertScorecardBundle Integrity

```bash
git diff c34c6bd..HEAD -- src/liquidationheatmap/models/scorecard.py
```

MUST be empty or minimal. The existing model must NOT be modified (spec-041/042 contract).

### Step 11: Atomic Write Safety

Verify the artifact writer:
1. Writes to a temp file first (e.g., `latest.json.tmp` or `tempfile.NamedTemporaryFile`)
2. Uses `os.replace()` or `shutil.move()` for atomic rename
3. Never leaves partial files on crash

### Step 12: Quality Classifier Logic

Verify status transitions:
- No artifact file on disk → `UNAVAILABLE`
- Artifact exists, schema invalid → `BLOCKED`
- Artifact exists, schema valid, stale (age > freshness_sla_secs) → `DEGRADED`
- Artifact exists, schema valid, coverage gaps > 0 → `DEGRADED`
- Artifact exists, schema valid, fresh, no gaps → `HEALTHY`

### Step 13: Calibration Metadata Completeness

Verify the calibration extraction covers at minimum:
- `touch_band` or equivalent adaptive parameter → kind=`derived`
- `bootstrap` (n_bootstrap, seed_policy) → kind=`method_constant`
- `freshness_sla_secs` → kind=`governance_constant`

Each entry must have ALL CalibrationMetadataEntry fields: `kind`, `name`, `value`, `method`, `input_count`, `reason`.

### Step 14: Docker/Compose Check

```bash
grep -A5 "scorecard\|/app/data" docker-compose.yml 2>/dev/null
```

Verify the scorecard artifacts path is accessible inside the container through existing or new volume mount.

---

## SPECIFIC DEEP-DIVE CHECKS

### Generator Script (scripts/generate-scorecard-evidence.py)

1. Does it require and load real price-path JSON via `--price-path`?
2. Does it fail closed on: missing snapshot manifests, missing price path, invalid JSON, invalid bundle, blocking issues?
3. Does it avoid fabricated experts/symbols/observation counts?
4. Is `--enable-adaptive` / non-adaptive behavior coherent?
5. Does it write both `latest.json` AND `latest-summary.json`?
6. Does it write run-specific artifacts under `runs/{run_id}/`?
7. Exit code: 0 on success, non-zero on any failure?

### Runtime Module (src/liquidationheatmap/scorecard/runtime.py)

1. Is deterministic JSON actually reproducible? (sort_keys=True, no timestamps in hash input)
2. Are atomic writes implemented correctly? (temp file → os.replace)
3. Is quality classification correct for all edge cases?
4. Does `scorecard_status_from_details()` aggregate all quality dimensions?
5. Does it handle corrupt/truncated JSON gracefully?

### Ops Router (src/liquidationheatmap/api/routers/ops.py)

1. Does `/ops/scorecard/latest` return correct envelope for all 4 states?
2. Does `/ops/summary` include only compact scorecard data?
3. Does missing scorecard degrade provider summary without claiming execution ownership?
4. Is freshness_sla_secs = 86400 (not the default 60 from OpsEnvelope)?

### Test Quality

1. Are there actual RED tests (tests that fail without implementation)?
2. Do tests use real-ish data structures, not empty mocks that always pass?
3. Are all 4 status transitions tested?
4. Is reproducibility tested with actual byte comparison?
5. Is the backward compat test (T008b) real — does it load an actual spec-041/042 bundle?
6. Is the read-only test (T026b) real — does it send POST/PUT/DELETE and assert 405?

---

## SEVERITY CLASSIFICATION

- **CRITICAL**: Test failures, contract violations, fabricated data, broken imports, missing fail-closed behavior
- **HIGH**: Missing FR coverage, wrong status transitions, schema mismatch with data-model.md
- **MEDIUM**: Missing edge case tests, suboptimal error messages, minor drift from contract
- **LOW**: Style issues, naming inconsistencies, missing docstrings

---

## FIX PROTOCOL

1. For CRITICAL/HIGH issues: fix immediately, commit with `fix(scorecard): <description>`
2. For MEDIUM issues: fix if simple (<10 LOC), otherwise document
3. For LOW issues: document only, do not fix

After all fixes:
```bash
uv run pytest -v --tb=short
uv run ruff check . && uv run ruff format --check .
```

---

## KNOWN NON-SCOPE DIRTY FILES

The workspace has unrelated dirty files from previous work:
- `docs/EXCHANGE_COMPARISON.md`, `docs/EXCHANGE_INTEGRATION.md`
- `scripts/collect_liquidations.py`, `scripts/continuous_consumer.py`, `scripts/validate_hyperliquid.py`
- `src/exchanges/hyperliquid.py`, `src/liquidationheatmap/streams/liquidations.py`
- `tests/test_exchanges/test_hyperliquid.py`, `tests/test_ws_liquidation_stream.py`

Ignore them unless spec-043 changes depend on them.

---

## FINAL REPORT

After review, produce a structured report:

```
## spec-043 Review Report

### Commit Inventory
- Phase 1: <hash> <message>
- ...

### Test Results
- Total: N | Passed: N | Failed: N | Skipped: N
- New tests added: N
- Regression: PASS/FAIL

### Contract Compliance: PASS/FAIL
- FR coverage: N/18
- NFR coverage: N/6

### Issues Found
| # | Severity | Description | Fixed? |
|---|----------|-------------|--------|

### Fixes Applied
- <hash> <message>
- ...

### Verdict: APPROVED / NEEDS WORK
```

If verdict is APPROVED, add a final commit:
```bash
git commit --allow-empty -m "review(scorecard): spec-043 external review PASSED

Reviewed by Claude. N issues found, N fixed.
FR coverage: N/18, NFR coverage: N/6.
All tests green. Contract compliance verified.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## GO

Start with Step 1. Work through all 14 steps plus deep-dive checks. Fix issues as you find them. Produce the final report.
