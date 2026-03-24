# Implementation Plan: Reserved-Margin Validation & Portfolio-Margin Solver

**Branch**: `027-reserved-margin-validation` | **Date**: 2026-03-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/027-reserved-margin-validation/spec.md`

## Summary

Validate the sidecar's reserved-margin formula against Hyperliquid's `clearinghouseState` API for 10+ outlier users, detect portfolio-margin accounts, implement a portfolio-margin solver, and upgrade the cross-margin solver to V1.1 incorporating the validated reserved-margin formula. This is a research-heavy feature: the formula must be reverse-engineered from observable API behavior because no public documentation or academic literature exists for Hyperliquid's open-order margin reserve semantics.

## Technical Context

**Language/Version**: Python 3.11+ (existing sidecar codebase)
**Primary Dependencies**: httpx (async HTTP for HL Info API), msgpack, zstandard, pytest
**Storage**: JSON artifacts in `data/validation/`, existing DuckDB for heatmap cache (read-only for this spec)
**Testing**: pytest (47 existing sidecar tests, 90% coverage)
**Target Platform**: Linux server (local development)
**Project Type**: single
**Performance Goals**: API validation is batch/offline — no latency budget. Solver V1.1 must maintain <100ms per user batch.
**Constraints**: Hyperliquid Info API rate limit (~10-20 req/min), no auth required for public addresses
**Scale/Scope**: 10+ outlier users for validation, ~340k accounts in full population (ETH 7d anchor)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| 1. Mathematical Correctness (MUST) | PASS | Margin formulas validated against API ground truth (1% tolerance). Tiered MMR with Decimal-safe arithmetic. |
| 2. Test-Driven Development (MUST) | PASS | TDD Red-Green-Refactor enforced. 47 existing tests as baseline. |
| 3. Exchange Compatibility (MUST) | PASS | Core goal: match Hyperliquid clearinghouse exactly. API as oracle. |
| 4. Performance Efficiency (SHOULD) | PASS | Batch offline validation. Solver V1.1 reuses existing vectorized path. |
| 5. Data Integrity (MUST) | PASS | All validation artifacts are JSON with metadata provenance. Immutable comparison reports. |
| 6. Graceful Degradation (SHOULD) | PASS | FR-009 requires retry logic and partial-result reporting for API failures. |
| 7. Progressive Enhancement (SHOULD) | PASS | US1 (validation) is independent of US2/US3 (portfolio margin). US4 depends on US1. |
| 8. Documentation Completeness (MUST) | PASS | Validation reports document every margin deviation and factor attribution. |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```
specs/027-reserved-margin-validation/
├── plan.md              # This file
├── research.md          # Phase 0: API response structure, formula candidates, portfolio margin detection
├── data-model.md        # Phase 1: entities, validation report schema
├── quickstart.md        # Phase 1: how to run validation and solver
├── contracts/           # Phase 1: API client interface, solver interface
└── tasks.md             # Phase 2: implementation tasks (created by /speckit.tasks)
```

### Source Code (repository root)

```
src/liquidationheatmap/hyperliquid/
├── sidecar.py           # EXISTING: solver V1, position reconstructor (1697 LOC)
├── api_client.py        # NEW: Hyperliquid Info API client (clearinghouseState, meta)
├── margin_validator.py  # NEW: compare sidecar vs API margin values, factor attribution
├── portfolio_solver.py  # NEW: portfolio-margin solver (net risk, PMR threshold)
└── __init__.py          # EXISTING

scripts/
├── validate_reserved_margin.py   # NEW: CLI for batch margin validation against API
└── analyze_hl_reserved_margin_outliers.py  # EXISTING (spec-026)

tests/
├── test_hyperliquid_sidecar.py   # EXISTING: 47 tests
├── test_margin_validator.py      # NEW: validation report generation, factor attribution
├── test_portfolio_solver.py      # NEW: portfolio margin solver
└── test_api_client.py            # NEW: API client (with real API + mock fallback)

data/validation/
├── hl_reserved_margin_outliers_eth_sample.json    # EXISTING (spec-026 artifact)
├── hl_reserved_margin_proxy_eth_sample.json       # EXISTING (spec-026 artifact)
├── hl_open_order_margin_gap_eth_7d.json           # EXISTING (spec-026 artifact)
├── margin_validation_report_*.json                # NEW: per-run validation reports
└── portfolio_margin_accounts_*.json               # NEW: detected PM accounts
```

**Structure Decision**: Single project, extending the existing `src/liquidationheatmap/hyperliquid/` module. No new packages needed. New files are additive — no restructuring of existing code.

## Constitution Re-Check (Post-Design)

*Re-evaluated after Phase 1 design artifacts are complete.*

| Principle | Status | Post-Design Notes |
|-----------|--------|-------------------|
| 1. Mathematical Correctness (MUST) | PASS | 4 candidate formulas defined in research.md. Validation against API oracle. Tiered MMR arithmetic reuses existing `_get_margin_tier()`. |
| 2. Test-Driven Development (MUST) | PASS | 3 new test files defined in contracts. TDD guard enforced. |
| 3. Exchange Compatibility (MUST) | PASS | API `clearinghouseState` is the ground truth. Per-position `marginUsed` + `liquidationPx` comparison. |
| 4. Performance Efficiency (SHOULD) | PASS | Batch validation offline. Solver V1.1 adds one subtraction to existing path — negligible overhead. |
| 5. Data Integrity (MUST) | PASS | All validation reports include metadata provenance (anchor path, timestamp, API query time). |
| 6. Graceful Degradation (SHOULD) | PASS | `get_clearinghouse_states_batch` returns `dict[str, Result | Exception]` — partial results on API failures. |
| 7. Progressive Enhancement (SHOULD) | PASS | US1 -> US4 dependency chain allows incremental delivery. US2/US3 (portfolio) independent from US1/US4 (cross-margin). |
| 8. Documentation Completeness (MUST) | PASS | quickstart.md, data-model.md, 3 contract files. Success criteria verification commands documented. |

**Post-design gate result**: PASS — design is consistent with constitution. No violations detected.

## Complexity Tracking

No constitution violations. No complexity justification needed.
