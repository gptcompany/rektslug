# Tasks: Counterflow Profile

**Input**: `specs/021-counterflow-profile/spec.md`
**Dependencies**: `spec-020` visual harness design
**Feature Type**: Provider profile / integration planning

## Phase 1: Inventory

- [ ] T001 Inventory existing Counterflow URLs, scripts, and capture behavior in repo
- [ ] T002 Document which outputs are data-comparison-ready vs visual-reference-only
- [ ] T003 Document TradingView Lightweight constraints that matter for parity work

## Phase 2: Profile Definition

- [ ] T004 Define manifest/provider metadata for Counterflow
- [ ] T005 Define how Counterflow should appear in comparison reports
- [ ] T006 Define whether Counterflow is data-source, visual-reference, or both

## Phase 3: Harness Alignment

- [ ] T007 Define how Counterflow will plug into `spec-020` screenshot/score manifests
- [ ] T008 Identify adapter work required because of Lightweight Charts rendering
- [ ] T009 Define a minimal smoke run for future implementation
- [ ] T010 Decide whether a local Lightweight Charts smoke page is needed at all
- [ ] T011 If needed, document installation choice and validation gates before implementation

Suggested validation gates if Lightweight is introduced later:
- library loads locally without a repo-wide frontend build migration
- a trivial chart renders reproducibly
- Playwright can capture it reliably
- the output is compatible with `spec-020` screenshot scoring

## Phase 4: Documentation

- [ ] T012 Document the final architectural role of Counterflow in repo docs/spec notes
