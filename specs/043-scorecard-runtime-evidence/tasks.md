# Tasks: Scorecard Runtime Evidence Plane

**Input**: Design documents from `/specs/043-scorecard-runtime-evidence/`
**Prerequisites**: spec.md, plan.md, data-model.md, contracts/
**Tests**: TDD required. RED tests before implementation.

## Format: `[ID] [Markers] [Story] Description`

- **[P]**: Can run in parallel; different files and no dependency conflict
- **[US]**: User story reference

---

## Phase 1: Contracts and Test Scaffolding

- [ ] T001 Create `tests/test_scorecard/test_runtime_evidence.py`
- [ ] T002 [P] Create `tests/integration/test_ops_scorecard_endpoint.py`
- [ ] T003 Create `src/liquidationheatmap/scorecard/runtime.py`
- [ ] T004 [P] Create `src/liquidationheatmap/scorecard/calibration.py`
- [ ] T005 [P] Create `scripts/generate-scorecard-evidence.py`

---

## Phase 2: Runtime Evidence Models

- [ ] T006 RED: write model/contract tests for scorecard evidence summary and calibration metadata
- [ ] T007 Implement scorecard evidence summary helpers in `src/liquidationheatmap/scorecard/runtime.py`
- [ ] T008 Implement calibration metadata helpers in `src/liquidationheatmap/scorecard/calibration.py`
- [ ] T009 GREEN: verify runtime evidence model tests pass

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
- [ ] T018 Wire `ScorecardPipeline.run_from_retained_snapshots(..., enable_adaptive=True)`
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

---

## Phase 6: Summary Integration

- [ ] T027 [US5] RED: write failing test that `/ops/summary` includes `scorecard_status`
- [ ] T028 [US5] RED: write failing test that `/ops/summary` includes compact `scorecard_summary`
- [ ] T029 Wire scorecard status into `/ops/summary`
- [ ] T030 Ensure summary remains compact and does not embed full scorecard bundle
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

- [ ] T044 RED: write compose/deploy test that API can read scorecard artifact path through `/app/data`
- [ ] T045 Update compose/deploy checks if needed
- [ ] T046 GREEN: verify compose/deploy tests pass

---

## Phase 10: Documentation and Cross-Repo Smoke

- [ ] T047 Update architecture/runtime docs with scorecard evidence endpoint
- [ ] T048 Add quickstart command to docs index or runtime docs
- [ ] T049 Run targeted tests: scorecard runtime, ops endpoint, ops summary, compose config
- [ ] T050 Run cross-repo smoke against `nautilus_dev` cockpit provider
- [ ] T051 Record final status in checklist

---

## Dependency Order

1. T001-T005 setup
2. T006-T009 models/helpers
3. T010-T014 artifact writer
4. T015-T020 generator
5. T021-T031 endpoint + summary
6. T032-T043 quality + calibration
7. T044-T051 deployment/docs/smoke
