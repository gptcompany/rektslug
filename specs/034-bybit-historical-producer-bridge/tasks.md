# Tasks: spec-034 Bybit Historical Producer Bridge

## Phase 1: Contract Freeze

- [ ] T001 Freeze normalized historical layout for Bybit producer inputs
- [ ] T002 Freeze source provenance fields required for normalization outputs
- [ ] T003 Define channel-by-channel historical requirements for `bybit_standard`
  and `depth_weighted`

## Phase 2: Readers and Normalizers

- [ ] T004R RED: Add failing tests for historical source path resolution
- [ ] T005 Implement historical raw readers for Bybit downloader source files
- [ ] T006 Implement normalized output writers for producer-readable historical inputs
- [ ] T007 Persist normalization metadata including source path and digest references

## Phase 3: Readiness Integration

- [ ] T008R RED: Add failing tests proving normalized historical windows clear
  `blocked_source_unverified`
- [ ] T009 Update `BybitReadinessGate` to recognize normalized historical inputs
- [ ] T010 Keep explicit `blocked_source_missing` behavior for uncovered windows

## Phase 4: Producer Integration

- [ ] T011R RED: Add failing tests for historical Bybit artifact export using normalized inputs
- [ ] T012 Update the Bybit producer to resolve historical normalized inputs
- [ ] T013 Preserve existing `spec-030` manifest/artifact semantics

## Phase 5: Validation and Handoff

- [ ] T014 Produce sample historical manifests for `bybit_standard`
- [ ] T015 Produce sample historical manifests for `depth_weighted`
- [ ] T016 Validate deterministic rerun behavior from identical normalized inputs
- [ ] T017 Update `CURRENT_SCOPE.md` and roadmap references after validation
