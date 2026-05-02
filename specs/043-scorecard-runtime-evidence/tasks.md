# Tasks: Scorecard Runtime Evidence Plane

**Input**: Design documents from `/specs/043-scorecard-runtime-evidence/`
**Prerequisites**: spec.md, plan.md, data-model.md, contracts/
**Tests**: TDD required. RED tests before implementation.

## Format: `[ID] [Markers] [Story] Description`

- **[P]**: Can run in parallel; different files and no dependency conflict
- **[US]**: User story reference

---

## Phase 1: Contracts and Test Scaffolding

- [ ] T001 Create `tests/test_scorecard/test_runtime_evidence.py` (empty test module with imports)
- [ ] T002 [P] Create `tests/integration/test_ops_scorecard_endpoint.py` (empty test module)
- [ ] T003 Create `src/liquidationheatmap/scorecard/runtime.py` (empty module stub, no logic)
- [ ] T004 [P] Create `src/liquidationheatmap/scorecard/calibration.py` (empty module stub, no logic)
- [ ] T005 [P] Create `scripts/generate-scorecard-evidence.py` (argparse skeleton, no pipeline logic)

---

## Phase 2: Runtime Evidence Models

- [ ] T006 RED: write model/contract tests for scorecard evidence summary and calibration metadata
- [ ] T007 Implement scorecard evidence summary helpers in `src/liquidationheatmap/scorecard/runtime.py`
- [ ] T008 Implement calibration metadata helpers in `src/liquidationheatmap/scorecard/calibration.py`
- [ ] T008b RED: write test that existing `ExpertScorecardBundle` from spec-041/042 loads without error in new runtime layer (FR-016 backward compat)
- [ ] T009 GREEN: verify runtime evidence model tests pass (including T008b)

---

## Phase 3: Artifact Writer

- [ ] T010 RED: write failing test that valid `ExpertScorecardBundle` writes `latest.json` and `latest-summary.json`
- [ ] T011 RED: write failing reproducibility test proving same inputs produce byte-identical JSON
- [ ] T012 Implement deterministic canonical JSON writer with atomic temp-file rename
- [ ] T013 Implement reproducibility hash calculation
- [ ] T014 GREEN: verify artifact writer tests pass

---

## Phase 4: Generator CLI

- [ ] T015 RED: write failing CLI test for successful adaptive evidence generation
- [ ] T016 RED: write failing CLI test that missing retained snapshots exits non-zero and does not write green artifact
- [ ] T017 Implement `scripts/generate-scorecard-evidence.py`
- [ ] T018 Add `ScorecardPipeline.run_from_retained_snapshots(snapshot_root, price_path, enable_adaptive=True)` method if not present in spec-041/042; wire into generator CLI
- [ ] T019 Persist input provenance and generation command metadata
- [ ] T020 GREEN: verify generator tests pass

---

## Phase 5: Ops Endpoint

- [ ] T021 [US1] RED: write failing integration test for `GET /ops/scorecard/latest` returning `HEALTHY` from a valid artifact
- [ ] T022 [US1] RED: write failing integration test for missing artifact returning `503 UNAVAILABLE`
- [ ] T023 [US1] RED: write failing integration test for invalid schema returning fail-closed status
- [ ] T024 Add `/ops/scorecard/latest` route in `src/liquidationheatmap/api/routers/ops.py`
- [ ] T025 Validate artifact against `ExpertScorecardBundle` before healthy status
- [ ] T026 GREEN: verify endpoint tests pass
- [ ] T026b RED: write test that /ops/scorecard/latest rejects POST/PUT/DELETE with 405 (FR-017 read-only)

---

## Phase 6: Summary Integration

- [ ] T027 [US5] RED: write failing test that `/ops/summary` includes `scorecard_status`
- [ ] T028 [US5] RED: write failing test that `/ops/summary` includes compact `scorecard_summary`
- [ ] T029 Wire scorecard status into `/ops/summary`
- [ ] T030 Assert /ops/summary response does not contain full scorecard bundle fields (NFR-005: slice details, calibration_metadata, artifact_links excluded)
- [ ] T031 GREEN: verify summary tests pass

---

## Phase 7: Data Quality Status

- [ ] T032 [US4] RED: write failing test for stale artifact -> `DEGRADED`
- [ ] T033 [US4] RED: write failing test for coverage gaps -> `DEGRADED`
- [ ] T034 [US4] RED: write failing test for blocking schema issue -> `BLOCKED`
- [ ] T035 Implement scorecard quality classifier
- [ ] T036 Emit blocking issues and coverage gap count
- [ ] T037 GREEN: verify quality status tests pass

---

## Phase 8: Calibration Metadata

- [ ] T038 [US3] RED: write failing test that calibration metadata labels derived values
- [ ] T039 [US3] RED: write failing test that bootstrap settings are labeled `method_constant`
- [ ] T040 [US3] RED: write failing test that freshness SLA is labeled `governance_constant`
- [ ] T041 Implement calibration metadata extraction for adaptive parameters
- [ ] T042 Implement method/governance constant labels
- [ ] T043 GREEN: verify calibration tests pass

---

## Phase 9: Docker and Deploy Guardrails

- [ ] T044 RED: write test that verifies `data/validation/scorecards/` is mounted at `/app/data/validation/scorecards/` in docker-compose.yml volume config (parse YAML, no container needed)
- [ ] T045 Update docker-compose.yml volumes if scorecard path is not already covered by existing `/app/data` mount
- [ ] T046 GREEN: verify compose volume test passes

---

## Phase 10: Documentation and Cross-Repo Smoke

- [ ] T047 Update architecture/runtime docs with scorecard evidence endpoint
- [ ] T048 Add quickstart command to docs index or runtime docs
- [ ] T048b Verify endpoint response time <500ms with local artifact (NFR-001, manual benchmark)
- [ ] T048c Verify generation completes <30s for BTC/ETH retained data (NFR-002, manual benchmark)
- [ ] T048d Verify no new external ML/statistics dependencies added to pyproject.toml (NFR-006)
- [ ] T049 Run targeted tests: scorecard runtime, ops endpoint, ops summary, compose config
- [ ] T050 Run cross-repo smoke against `nautilus_dev` cockpit provider
- [ ] T051 Record final status in checklist

---

## Dependency Order

1. T001-T005 setup
2. T006-T008b-T009 models/helpers (T008b RED before T009 GREEN)
3. T010-T014 artifact writer
4. T015-T020 generator
5. T021-T031 endpoint + summary
6. T032-T043 quality + calibration
7. T044-T051 deployment/docs/smoke
