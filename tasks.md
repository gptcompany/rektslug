# Tasks: Reserved-Margin Validation & Portfolio-Margin Solver

**Organization**: Tasks grouped by user story. US1/US4 are P1 (MVP), US2/US3 are P2.

**Research-informed adjustments**:
- `crossMaintenanceMarginUsed` is the correct comparison target (NOT `totalMarginUsed` which is IM)
- Reserved margin for resting orders is NOT exposed by `clearinghouseState` API — hidden field
- MMR formula `notional / (2 * maxLeverage)` already validated to 0.25% mean deviation (7/8 within 1%)
- `liquidationPx` is available per-position from the same API call — free validation data
- 0/9 outlier users are portfolio-margin — US3 may be blocked (mock data required)

### Phase 1: Setup
- [ ] T001 [P] Create API-response DTOs and Validation Report types in `models.py`: MarginMode enum, MarginSummary (with cross_maintenance_margin_used), CrossMarginSummary, ApiPosition, PortfolioMarginSummary, AssetMeta, MarginTier, ClearinghouseUserState, PositionMarginComparison, MarginValidationResult, MarginValidationReport
- [ ] T002 [P] Extract `get_margin_tier()` and `compute_position_maintenance_margin()` as standalone functions in `margin_math.py` (from SidecarPositionReconstructor instance methods). Update `sidecar.py` to delegate (call sites at `:1619` and `:1641`). Verify existing 47 tests pass.

### Phase 2: API Client
- [ ] T003 Write failing tests for HyperliquidInfoClient in `tests/test_api_client.py`
- [ ] T004 Implement HyperliquidInfoClient in `api_client.py`: get_clearinghouse_state(), get_asset_meta(), get_clearinghouse_states_batch() with `aiohttp` async, rate limiting (10 req/min), exponential backoff
- [ ] T005 Green tests
- [ ] T006 Update `__init__.py` exports

### Phase 3: US1 — MMR Validation (P1, MVP)
- [ ] T007 Write failing tests in `tests/test_margin_validator.py` (mmr_within_tolerance, liq_px_comparison, batch_report)
- [ ] T008 Implement validate_user() — compute MMR from API-reported positions (same-instant, NOT ABCI snapshot), compare vs crossMaintenanceMarginUsed + liquidationPx
- [ ] T009 Implement validate_batch() — aggregation, tolerance_rate
- [ ] T010 Green tests
- [ ] T011 Create CLI script `scripts/validate_reserved_margin.py`
- [ ] T012 Run live validation with 9 outlier + 1-2 control users → SC-001

### Phase 4: US4 — Solver V1.1 & Reserved Margin Formula Selection (P1)
- [ ] T013 Write failing tests in `tests/test_hyperliquid_sidecar.py` (subtracts_reserved, matches_v1_no_orders, estimate_from_bounds)
- [ ] T014 Add `reserved_margin=0.0` param to solve_liquidation_price() in `sidecar.py`
- [ ] T015 Implement `estimate_reserved_margin(orders, candidate_type)` in `margin_math.py` supporting Candidates A, B, C, and D (from research.md).
- [ ] T016 Execute Solver V1.1 iterating on all 4 candidates for 9 outlier users and calculate deviation vs API liquidationPx.
- [ ] T017 Select the winning candidate (minimizes average deviation) and set as default in V1.1.
- [ ] T018 Green tests
- [ ] T019 Compare V1 vs V1.1 liquidationPx against API → SC-004

### Phase 5: US2 — PM Detection (P2)
- [ ] T020 Write failing tests (detect cross/portfolio/isolated mode). *Note: Use mock JSON payload based on Hyperliquid docs, since live PM accounts are not available in our outlier sample.*
- [ ] T021 Implement detect_margin_mode()
- [ ] T022 Add --detect-modes to CLI (scan top 50 accounts, bounded)
- [ ] T023 Green tests

### Phase 6: US3 — PM Solver (P2, LIKELY DEFERRED)
- [ ] T024 Write failing tests (netting, PMR threshold, PM liqPx)
- [ ] T025 Implement compute_portfolio_margin()
- [ ] T026 Implement solve_portfolio_liquidation_price()
- [ ] T027 Green tests
- [ ] T028 Live validation if PM accounts found → SC-003

### Phase 7: Polish
- [ ] T029 Full test suite run (`pytest`)
- [ ] T030 Final report generation
- [ ] T031 Update contracts and `research.md`
