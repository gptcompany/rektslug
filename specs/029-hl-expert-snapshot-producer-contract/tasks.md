# Tasks: Hyperliquid Expert Snapshot Producer Contract

**Input**: `specs/029-hl-expert-snapshot-producer-contract/spec.md`
**Dependencies**: `spec-026`, local Hyperliquid sidecar builder paths, and `/media/sam/1TB/nautilus_dev/specs/061-liquidation-map-expert-evaluator/spec.md`
**Feature Type**: Contract hardening + producer export implementation

## Phase 1: Contract Lock-In

- [x] T001 Re-read `spec-029`, the `spec-061` consumer boundary, and the current Hyperliquid runbook decisions
- [x] T002 Confirm and record the canonical policy tags:
  - `v1` = canonical
  - `v2` = `shadow/control`
  - `v3` / `v4` / `v5` = experimental
- [x] T003 Confirm the current producer touchpoints are:
  - `scripts/precompute_hl_sidecar.py`
  - `scripts/compare_hl_sidecar_variants.py`
  - `docs/runbooks/hyperliquid-liqmap-checkpoint.md`
- [x] T004 Freeze the minimum `ExpertSnapshotArtifact` field set and the minimum `ExpertSnapshotManifest` field set in the spec folder or implementation docs
- [x] T004A Freeze canonical timestamp semantics:
  - `snapshot_ts` = exported evaluation-point identity
  - `run_ts` = actual producer execution timestamp
  - UTC RFC 3339 / ISO8601 with `Z` suffix
- [x] T004B Freeze the manifest rule that all five expert channels (`v1`..`v5`) are always present with explicit availability status

## Phase 2: Schema And Export Primitives (TDD)

- [x] T005R RED: Write failing tests for expert snapshot schema validation:
  - test that a well-formed artifact passes validation
  - test that an artifact missing a required field is rejected
  - test that a malformed or missing bucket grid is rejected (FR-004)
  - test that numeric fields use float64 precision (NFR-001)
- [x] T005 Create a producer-side schema module or helper for expert snapshot normalization
- [x] T005P Define and enforce float64 precision for `reference_price`, `bucket_grid`, and distribution values in the schema module
- [x] T006 Define the machine-readable bucket-grid representation for exported artifacts
- [x] T006A Define whether the artifact uses explicit `price_levels` or canonical `min/max/step` reconstruction, and document it as the only accepted MVP grid form
- [x] T007 Define the `generation_metadata` contract with at least:
  - `run_id`
  - `run_reason`
  - `run_ts`
  - `last_actual_run_ts`
  - `producer_version`
- [x] T008 Define the `source_metadata` contract with at least:
  - source path or capture root
  - source timestamp/anchor when available
  - builder family / logic family
  - reconstruction notes where relevant
- [x] T008A Define immutable `input_identity` fields for deterministic rerun claims:
  - source manifest id
  - capture id or retained snapshot id
  - content digest/checksum where applicable
- [x] T009 Create validation helpers that reject malformed or contract-incomplete expert artifacts

## Phase 3: Manifest-First Export Layout (TDD)

- [x] T010R RED: Write failing tests for manifest and export layout:
  - test that a manifest always lists all five expert channels (FR-021)
  - test that missing experts have explicit `availability_status` (FR-022)
  - test that source/decode failures are machine-readable in manifest (FR-015)
  - test that a consumer can parse the manifest using only `json.load` without importing any `src/liquidationheatmap/` module (FR-016)
  - test that timestamp-derived paths use canonical `snapshot_ts` format
- [x] T010 Create the export root `data/validation/expert_snapshots/hyperliquid/`
- [x] T011 Define and implement timestamp-addressable artifact layout under `artifacts/{symbol}/{timestamp}/`
- [x] T012 Define and implement manifest layout under `manifests/{symbol}/`
- [x] T013 Define and implement batch/backfill record layout under `batches/`
- [x] T014 Ensure manifests always list all five expert channels and report missing experts explicitly rather than relying on missing files
- [x] T015 Ensure manifests report source/decode failures explicitly and machine-readably
- [x] T015A Ensure all timestamp-derived paths and manifest filenames are generated from canonical `snapshot_ts`

## Phase 4: Producer Run Metadata And Scheduling Semantics (TDD)

- [x] T016R RED: Write failing tests for run metadata and scheduling:
  - test that run metadata contains `run_id`, `run_reason`, `run_ts`, `last_actual_run_ts`
  - test that `baseline`, `extra`, `manual`, `backfill` are the accepted run kinds
  - test that an extra run re-anchors `last_actual_run_ts` for the next baseline
  - test that `run_ts` and `snapshot_ts` remain distinct during backfill
- [x] T016 Define the producer-side run kinds:
  - `baseline`
  - `extra`
  - `manual`
  - `backfill`
- [x] T017 Define metadata rules that preserve the agreed baseline semantics:
  - cadence measured from `last_actual_run_ts`
  - extra runs re-anchor the next baseline
- [x] T018 Implement recording of run identity and prior-run linkage in exported metadata
- [x] T019 Document how current 15m producer cadence relates to future evaluator-side 5m sampling cadence so consumer boundary stays explicit

## Phase 5: Current Builder Integration (TDD)

- [x] T020R RED: Write failing tests for builder integration and v2 shadow semantics:
  - test that `v1` artifact carries `research_policy_tag: "canonical"`
  - test that `v2` artifact carries `research_policy_tag: "shadow/control"`
  - test that exported artifacts do not contain `data/cache/` path references
  - test that all exported distributions are normalized onto the declared common grid (FR-024, T024A)
- [x] T020 Extract or wrap current distribution-normalization logic from `scripts/compare_hl_sidecar_variants.py` into a reusable producer export path
- [x] T021 Integrate current `v1` export into the new artifact/manifest layout
- [x] T022 Integrate current `v2` replay/control export into the new artifact/manifest layout while preserving explicit shadow semantics
- [x] T023 Integrate current experimental variant exports (`v3`, `v4`, `v5`) into the same layout or explicitly report them as unavailable where builder coverage is missing
- [x] T024 Ensure exported artifacts do not require consumer-side knowledge of cache naming conventions in `data/cache/`
- [x] T024A Ensure exported artifacts are already normalized onto the declared common grid and do not require consumer-side rebucketing for MVP

## Phase 6: Historical Backfill Contract (TDD)

- [x] T025R RED: Write failing tests for backfill coverage and gap reporting:
  - test that a backfill batch record contains interval, symbol set, expert set, coverage, and timeline policy
  - test that missing timestamps are reported as `gap` (no source data) vs `failure` (data present, not processable)
  - test that rerunning the same backfill with identical inputs produces deterministic manifests (apart from generation metadata)
  - test that `input_identity` fields match across deterministic reruns
- [x] T025 Define the first accepted backfill timeline policy:
  - fixed cadence aligned to producer baseline cadence
- [x] T026 Implement a bounded historical batch export path using that timeline policy
- [x] T027 Ensure each backfill batch records:
  - interval
  - symbol set
  - expert set
  - coverage
  - missing timestamps
  - missing experts
  - source/decode failures
- [x] T028 Ensure rerunning the same bounded backfill with the same inputs is deterministic apart from declared generation metadata, and prove input sameness via immutable `input_identity` fields

## Phase 7: Integration Validation And Consumer Handoff

- [x] T032 Produce one sample export batch that can be inspected by `nautilus_dev` without path heuristics
- [x] T033 Document the producer/consumer handoff contract in the `029` spec folder and/or runbook

## Completion Notes

- The producer side is complete only when the consumer can resolve expert
  artifacts by manifest, not by cache-path guessing.
- No task in this spec should add replay evaluation, ex-post labels, or
  weighting to `rektslug`.
- If a variant is unavailable for a timestamp, that is acceptable only if the
  manifest says so explicitly.
- TDD discipline: every implementation phase (2-6) begins with RED tests.
  Implementation tasks make those tests GREEN. Phase 7 is integration
  validation and handoff only.
