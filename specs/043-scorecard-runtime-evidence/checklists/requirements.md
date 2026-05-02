# Requirements Checklist: Scorecard Runtime Evidence Plane

**Feature**: 043-scorecard-runtime-evidence
**Created**: 2026-05-02

## Scope Validation

- [x] Read-only `rektslug` provider scope
- [x] No `nautilus_dev` execution controls
- [x] No trading decision or expert auto-selection
- [x] No new UI requirement
- [x] No ML dependency requirement

## Contract Coverage

- [x] Dedicated endpoint contract defined
- [x] Summary integration contract defined
- [x] Missing artifact fail-closed behavior defined
- [x] Stale/partial/invalid artifact status semantics defined
- [x] Calibration metadata policy defined

## TDD Coverage

- [x] Endpoint RED tests planned
- [x] Generator RED tests planned
- [x] Reproducibility RED tests planned
- [x] Calibration metadata RED tests planned
- [x] Docker/deploy guardrail tests planned

## Open Items

- [ ] Resolve OQ-001 schedule: manual CLI first or scheduled sidecar
- [ ] Resolve OQ-002 canonical price-path source
- [ ] Resolve OQ-003 scorecard freshness SLA default
