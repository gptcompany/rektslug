# Tasks: Counterflow Profile

**Input**: `specs/021-counterflow-profile/spec.md`
**Dependencies**: `spec-020` visual harness design
**Feature Type**: Provider profile / integration planning

## Phase 1: Inventory

- [x] T001 Inventory existing Counterflow URLs, scripts, and capture behavior in repo
- [x] T002 Document which outputs are data-comparison-ready vs visual-reference-only
- [x] T003 Document TradingView Lightweight constraints that matter for parity work

## Phase 2: Profile Definition

- [x] T004 Define manifest/provider metadata for Counterflow
- [x] T005 Define how Counterflow should appear in comparison reports
- [x] T006 Record the architectural decision that Counterflow is both data-source and visual-reference, with an asymmetrical role
- [x] T007 Define the expected `renderer_adapter=lightweight` contract for Counterflow

## Phase 3: Harness Alignment

- [x] T008 Define how Counterflow will plug into `spec-020` screenshot/score manifests
- [x] T009 Identify adapter work required because of Lightweight Charts rendering
- [x] T010 Define a minimal smoke run for future implementation
- [x] T011 Decide whether a local Lightweight Charts smoke page is needed at all
- [x] T012 If needed, document installation choice and validation gates before implementation

Suggested validation gates if Lightweight is introduced later:
- library loads locally without a repo-wide frontend build migration
- a trivial chart renders reproducibly
- Playwright can capture it reliably
- the output is compatible with `spec-020` screenshot scoring

## Phase 4: Documentation

- [x] T013 Document the final architectural role of Counterflow in repo docs/spec notes

## Completion Notes

- Counterflow is now represented by explicit provider-profile metadata keyed as `bitcoincounterflow`, with display name `Bitcoin CounterFlow`, roles `data-source` and `visual-reference`, and default renderer adapter `lightweight`.
- Normalized comparison reports now expose provider-profile metadata separately from dataset payloads, so Counterflow no longer depends on URL inference or ad-hoc naming.
- The repo decision remains: no local Lightweight smoke page is added yet; if future live Counterflow visual wiring is needed, it must enter the shared harness as `renderer_adapter=lightweight` with its own installation and Playwright validation gate.
