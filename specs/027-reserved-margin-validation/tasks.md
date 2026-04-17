# Tasks: Reserved-Margin Validation & Portfolio-Margin Solver

**Input**: Design documents from `/specs/027-reserved-margin-validation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included (TDD enforced by project conventions).

**Organization**: Tasks grouped by user story. US1/US4 are P1 (MVP), US2/US3 are P2.

**Research-informed adjustments**:
- `crossMaintenanceMarginUsed` is the correct comparison target (NOT `totalMarginUsed` which is IM)
- Reserved margin for resting orders is NOT exposed by `clearinghouseState` API — hidden field
- MMR formula `notional / (2 * maxLeverage)` already validated to 0.25% mean deviation (7/8 within 1%)
- `liquidationPx` is available per-position from the same API call — free validation data
- 0/9 outlier users are portfolio-margin — US3 may be blocked

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Explore/Evolve - task requires multiple variants or iterations
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)

---

## Phase 1: Setup

**Purpose**: API-response DTOs, validation report types, and dependency setup (distinct from existing sidecar types `UserPosition`, `UserState`, `UserOrder` in sidecar.py)

- [-] T001 [P] Add `httpx` dependency to `pyproject.toml` and run `uv lock` (WAIVED: kept aiohttp as it was already present)
- [x] T002 [P] Create API-response DTOs in `src/liquidationheatmap/hyperliquid/models.py`: `MarginMode` enum, `MarginSummary` (with `cross_maintenance_margin_used` field), `CrossMarginSummary`, `ApiPosition`, `PortfolioMarginSummary`, `AssetMeta`, `MarginTier`, `ClearinghouseUserState`
- [x] T003 Create validation report types in `src/liquidationheatmap/hyperliquid/models.py` (append): `PositionMarginComparison` (with `liq_px_deviation_pct`), `FactorAttribution` (rename `resting_order_reserve` to `estimated_resting_order_reserve` to reflect best-effort nature), `MarginValidationResult`, `MarginValidationReport`
- [x] T004 [P] Extract `get_margin_tier()` and `compute_position_maintenance_margin()` as standalone functions in `src/liquidationheatmap/hyperliquid/margin_math.py` (refactored from `SidecarPositionReconstructor` instance methods at sidecar.py:1618-1638). Update sidecar.py to delegate to these functions. Verify existing tests pass: `uv run pytest tests/test_hyperliquid_sidecar.py -v`

**Checkpoint**: All shared types available. Margin math extracted as standalone functions. Existing 47 sidecar tests still green.

---

## Phase 2: Foundational — API Client

**Purpose**: Hyperliquid Info API client — blocks US1, US2, US4

- [x] T005 Write failing tests for `HyperliquidInfoClient` in `tests/test_api_client.py`: `test_get_clearinghouse_state_parses_cross_maintenance_margin`, `test_get_clearinghouse_state_parses_liquidation_px`, `test_get_clearinghouse_state_handles_timeout`, `test_get_asset_meta_returns_tiers`, `test_batch_query_returns_partial_on_failure`
- [x] T006 Implement `HyperliquidInfoClient` in `src/liquidationheatmap/hyperliquid/api_client.py`: `get_clearinghouse_state()` (parse `crossMaintenanceMarginUsed`, per-position `marginUsed` + `liquidationPx`), `get_asset_meta()`, `get_clearinghouse_states_batch()` with async client, rate limiting (10 req/min), exponential backoff on 429, partial-result dict return
- [x] T007 Green the tests from T005 — verify with `uv run pytest tests/test_api_client.py -v`
- [x] T008 Update `src/liquidationheatmap/hyperliquid/__init__.py` to export new modules (`models`, `api_client`, `margin_math`)

**Checkpoint**: API client operational. Can query live Hyperliquid API and parse all relevant fields including `crossMaintenanceMarginUsed` and `liquidationPx`.

---

## Phase 3: User Story 1 — MMR & LiquidationPx Validation (Priority: P1) MVP

**Goal**: Validate sidecar MMR formula against `crossMaintenanceMarginUsed` AND `liquidationPx` against `solve_liquidation_price()` output for 10+ users. Pass if 90%+ within 1%.

**Independent Test**: `uv run pytest tests/test_margin_validator.py -v && uv run python scripts/validate_reserved_margin.py --outliers data/validation/hl_reserved_margin_outliers_eth_sample.json --output /tmp/margin_report.json && jq '{user_count, tolerance_rate, passed}' /tmp/margin_report.json`

### Tests for User Story 1

- [x] T009 [US1] Write failing tests in `tests/test_margin_validator.py`: `test_validate_user_mmr_within_tolerance` (sidecar MMR matches API `crossMaintenanceMarginUsed` within 1%), `test_validate_user_liq_px_comparison` (sidecar liqPx vs API liqPx per position), `test_validate_user_outside_tolerance_gets_attribution` (deviation > 1% triggers `FactorAttribution`), `test_validate_batch_produces_report` (batch of 3 users produces `MarginValidationReport` with correct `tolerance_rate`)

### Implementation for User Story 1

- [x] T010 [US1] Implement `validate_user()` in `src/liquidationheatmap/hyperliquid/margin_validator.py`: query API via `HyperliquidInfoClient`, compute MMR from **API-reported positions and mark prices** (same-instant fair comparison, NOT ABCI snapshot data) using extracted `compute_position_maintenance_margin()` from `margin_math.py`. Compare against `crossMaintenanceMarginUsed`. Also compare `solve_liquidation_price()` vs API `liquidationPx` per position. Return `MarginValidationResult` with per-position `liq_px_deviation_pct`.
- [x] T011 [US1] Implement `attribute_factors()` in `src/liquidationheatmap/hyperliquid/margin_validator.py`: decompose MMR deviation > 1% into `FactorAttribution` (multi-tier rounding, funding timing, `estimated_resting_order_reserve`, unknown residual). Note: resting-order reserve is NOT visible in API — all attribution is best-effort estimation.
- [x] T012 [US1] Implement `validate_batch()` in `src/liquidationheatmap/hyperliquid/margin_validator.py`: batch validation with `MarginValidationReport` aggregation, `tolerance_rate`, `margin_mode_distribution`
- [x] T013 [US1] Green all tests from T009 — verify with `uv run pytest tests/test_margin_validator.py -v`
- [x] T014 [US1] Create CLI script `scripts/validate_reserved_margin.py`: load outlier JSON, call `validate_batch()`, write JSON report (including per-position `liquidationPx` comparison) to `--output` path

### Live Validation for User Story 1

- [x] T015 [US1] Run `scripts/validate_reserved_margin.py` against live API with 9 outlier users + 1-2 control users. Save to `data/validation/margin_validation_report.json`. First pass on 2026-03-31 failed SC-001 (`tolerance_rate = 0.6667`) and exposed whale outliers `0xd47587` / `0xfc667a`. After the tiered-MMR fix that parses live `marginTables` and infers missing maintenance deductions, the rerun reached `cross_margin tolerance_rate = 1.0000` with `0xd47587 = 0.0236%` and `0xfc667a = 0.0042%`. `passed_all_accounts` remains `false` because the two `isolated_margin` accounts are still out of tolerance.

**Checkpoint**: US1 cross-margin blocker is closed. `cross_margin` now satisfies SC-001, while `all_accounts` still fails because isolated-margin validation remains a separate residual issue. `liquidationPx` deviations remain available for US4.

---

## Phase 4: User Story 4 — Solver V1.1: LiquidationPx Accuracy (Priority: P1)

**Goal**: Improve `solve_liquidation_price()` accuracy by integrating estimated reserved margin from resting orders. Validate improvement by comparing V1 vs V1.1 `liquidationPx` against API values from US1 report.

**Research context**: Reserved margin is NOT exposed by API, so the formula is best-effort estimation using exposure bounds from `compute_resting_order_exposure_bounds()`. Validation is indirect: does V1.1 produce `liquidationPx` closer to API values than V1?

**Independent Test**: `uv run pytest tests/test_hyperliquid_sidecar.py -v -k "v1_1 or reserved"`

**Dependencies**: US1 must be complete (baseline `liquidationPx` deviations measured).

### Tests for User Story 4

- [x] T016 [US4] Write failing tests in `tests/test_hyperliquid_sidecar.py`: `test_solver_v1_1_subtracts_reserved_margin` (liqPx shifts closer to mark with reserved_margin > 0), `test_solver_v1_1_matches_v1_when_no_orders` (reserved_margin=0.0 produces identical result to V1), `test_estimate_reserved_margin_from_exposure_bounds` (given OrderExposureBounds with known exposure, estimate reserved margin using Candidate A)

### Implementation for User Story 4

- [x] T017 [US4] Add `reserved_margin: float = 0.0` parameter to `solve_liquidation_price()` in `src/liquidationheatmap/hyperliquid/sidecar.py`: subtract from `account_base` (`balance + other_pnl - reserved_margin`)
- [x] T018 [E] [US4] Implement `estimate_reserved_margin()` in `src/liquidationheatmap/hyperliquid/margin_math.py`: compute estimated reserved margin from `OrderExposureBounds.exposure_increasing_notional_upper_bound` using Candidate A (`notional / max_leverage`). This is a best-effort estimate — the true formula is not publicly documented.
- [x] T019 [US4] Green all tests from T016 — verify with `uv run pytest tests/test_hyperliquid_sidecar.py -v -k "v1_1 or reserved"`
- [x] T020 [US4] Compare V1 vs V1.1 `liquidationPx` against API values for US1 outlier users. Completed on 2026-03-31 and reranked after the tiered-MMR fix. **Candidate B remains the best scalar baseline among A-D** at `225/321` improved positions (`70.09%`), ahead of A (`66.67%`), D (`64.49%`), and C (`64.17%`). A later netting refinement introduced **Candidate E** (`0.1 * max(buy_side_mmr, sell_side_mmr)` per coin), which lifted the standard validation report to `168/174` improved `cross_margin` positions (`96.55%`) and `315/321` improved globally (`98.13%`).

**Checkpoint**: Solver V1.1 integrated. `liquidationPx` improvement is now materially better with the netted `Candidate E` heuristic. Current baseline: Candidate E.

---

## Phase 5: User Story 2 — Portfolio-Margin Account Detection (Priority: P2)

**Goal**: Detect which accounts use portfolio-margin mode and route them to the correct solver.

**Independent Test**: `uv run pytest tests/test_margin_validator.py -v -k "portfolio or margin_mode"` and `scripts/validate_reserved_margin.py --detect-modes`

**Dependencies**: Phase 2 (API client). Independent of US1/US4.

### Tests for User Story 2

- [x] T021 [US2] Write failing tests in `tests/test_margin_validator.py`: `test_detect_margin_mode_cross` (no `portfolioMarginSummary` returns `CROSS_MARGIN`), `test_detect_margin_mode_portfolio` (with `portfolioMarginSummary` returns `PORTFOLIO_MARGIN`), `test_detect_margin_mode_isolated` (all positions `leverage.type == "isolated"` returns `ISOLATED_MARGIN`)

### Implementation for User Story 2

- [x] T022 [US2] Implement `detect_margin_mode()` in `src/liquidationheatmap/hyperliquid/margin_validator.py`: classify account from parsed `ClearinghouseUserState` or raw API response. The current logic uses `userAbstraction` as the primary PM signal, falls back to `portfolioMarginSummary` when present, and then treats the account as `isolated_margin` only when all positions are isolated; mixed `cross + isolated` accounts remain `cross_margin`.
- [x] T023 [US2] Add `--detect-modes` flag to `scripts/validate_reserved_margin.py`: completed. The flag now supports both ranked-population scans and full-population reconstruction from the proxy report metadata, correcting stale feed paths when needed, and persists the detection artifact by default. A follow-up bugfix corrected mixed `cross + isolated` accounts that had been over-classified as `isolated_margin`; a later follow-up aligned detection with official Hyperliquid `userAbstraction` / `spotClearinghouseState` semantics. The corrected full scan rerun on 2026-03-31 succeeded for `394/397` users and found `355 cross_margin`, `36 isolated_margin`, and `3 portfolio_margin`, with abstraction counts `176 dexAbstraction`, `122 default`, `39 disabled`, `53 unifiedAccount`, `3 portfolioMargin`, `1 unknown`.
- [x] T024 [US2] Green tests from T021 — verify with `uv run pytest tests/test_margin_validator.py -v -k "portfolio or margin_mode"`

**Checkpoint**: SC-002 detection logic is validated and the broader scan is complete. On 2026-03-31, the corrected full reconstructed population scan found live PM examples (`3/397` `portfolio_margin`, `53/397` `unifiedAccount`), so US3/T029 is no longer blocked on account discovery. The remaining US3 work is solver implementation and live comparison against those observed PM accounts.

---

## Phase 6: User Story 3 — Portfolio-Margin Solver (Priority: P2)

**Goal**: Implement solver for portfolio-margin accounts using net-risk netting and PMR > 0.95 liquidation threshold.

**Independent Test**: `uv run pytest tests/test_portfolio_solver.py -v`

**Dependencies**: US2 (detection).

**RISK**: 0/9 outlier users were portfolio-margin, but the corrected full-population scan on 2026-03-31 found `3/397` PM accounts plus `53/397` `unifiedAccount` accounts. Live validation is now unblocked on account discovery, but the PM path still needs proper solver/routing work and may require additional API state beyond perp `clearinghouseState`.

### Tests for User Story 3

- [x] T025 [US3] Write failing tests in `tests/test_portfolio_solver.py`: completed with documented-PM scenarios for collateral support, PMR threshold, and a live-anchored HYPE short case derived from observed PM account `0xb1c4...`.

### Implementation for User Story 3

- [x] T026 [US3] Implement `compute_portfolio_margin()` in `src/liquidationheatmap/hyperliquid/portfolio_solver.py`: completed as a documented pre-alpha PM solver using `spotClearinghouseState`, `borrowLendUserState`, `allBorrowLendReserveStates`, API-anchored `availableAfterMaintenance`, and cross-maintenance MMR deltas.
- [x] T027 [US3] Implement `solve_portfolio_liquidation_price()` in `src/liquidationheatmap/hyperliquid/portfolio_solver.py`: completed with a target-price root solve over API-anchored PM liquidation value.
- [x] T028 [US3] Green tests from T025 — verified with `uv run pytest tests/test_portfolio_solver.py -v`
- [x] T029 [US3] Validate against live API for PM accounts found during US2: compare `liquidationPx` within 1% — SC-003. Validation now covers the full locally observed PM universe retained in repo artifacts. The live rerun against the three observed PM accounts still yields one comparable PM `liquidationPx` (`0xb1c4...` at `0.13%` error), while `0xdc00...` has no positions and `0xfc8b...` returns `null` `liquidationPx`. The review package now fails closed on fixture/observed-account coverage mismatch and retains the non-comparable accounts explicitly in `specs/027-reserved-margin-validation/review_package.json`.

**Checkpoint**: The PM solver, routing, and validation package are implemented and reviewable. SC-003 is closed against the retained observable PM account set because coverage is checked against the observed-account artifacts, all comparable live PM `liquidationPx` cases remain within tolerance, and the non-comparable accounts are retained explicitly in the review package.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Integration, documentation, and final validation

- [x] T030 Run full test suite: verified on 2026-03-31 with the expanded Hyperliquid suite (`tests/test_hyperliquid_sidecar.py`, `tests/test_api_client.py`, `tests/test_api_client_extension.py`, `tests/test_margin_validator.py`, `tests/test_margin_validator_extension.py`, `tests/test_portfolio_solver.py`, `tests/test_portfolio_solver_extension.py`, `tests/test_validate_reserved_margin_cli.py`) — `122 passed`
- [x] T031 Generate final validation report: rerun on 2026-03-31 via the healthy VPS/public `/info` fallback chain because the local consensus `/info` endpoint was unhealthy. Artifact refreshed at `data/validation/margin_validation_report.json`. The final rerun reflects the mixed `cross + isolated` comparison fix for `0x7717...`: `users_analyzed = 9`, `cross_margin tolerance_rate = 1.0000`, `mean_mmr_deviation_pct = 0.1784`, `passed_all_accounts = true`, `passed_cross_margin_only = true`. The last blocker fell to `0x7717... = 0.0331%`, so SC-001 is closed again, and SC-005 is also satisfied for this report (`0` users with `unknown` attribution exceeding 5% of total margin).
- [x] T032 Update contracts in `specs/027-reserved-margin-validation/contracts/` to reflect discovered API fields (`crossMaintenanceMarginUsed`, `crossMarginSummary`, `userAbstraction`, `spotClearinghouseState`, borrow/lend PM endpoints)
- [x] T033 Update `research.md` with final validation results, formula selection rationale, V1 vs V1.1 comparison conclusions, and the current operational note that live validation should prefer the VPS/public `/info` chain while the local consensus node is being stabilized

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately. T001+T002 and T004 can run in parallel (different files).
- **Phase 2 (API Client)**: Depends on Phase 1 (models + margin_math)
- **Phase 3 (US1 - MMR & LiqPx Validation)**: Depends on Phase 2 (API client) — **MVP**
- **Phase 4 (US4 - Solver V1.1)**: Depends on Phase 3 (baseline liqPx deviations from US1)
- **Phase 5 (US2 - PM Detection)**: Depends on Phase 2 (API client) — independent of US1/US4
- **Phase 6 (US3 - PM Solver)**: Depends on Phase 5 (detection) — live PM examples are now available, so implementation can proceed directly to live validation once the solver exists
- **Phase 7 (Polish)**: Depends on all desired phases complete

### User Story Dependencies

```
Phase 1 (Setup) — T001+T002 [P] T004
  └─> Phase 2 (API Client)
        ├─> Phase 3 (US1: MMR + LiqPx Validation) ──> Phase 4 (US4: Solver V1.1)
        └─> Phase 5 (US2: PM Detection) ──> Phase 6 (US3: PM Solver)
```

### Parallel Opportunities

- **Phase 1**: T001+T002 (models) and T004 (margin_math extraction) are [P] — different files
- **Post Phase 2**: US1/US4 chain and US2/US3 chain are fully independent
- **Within phases**: Test tasks are sequential within same file (no [P] — same file rule)

---

## Implementation Strategy

### MVP First (US1 Only) — Recommended

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: API Client (T005-T008)
3. Complete Phase 3: US1 MMR + LiqPx Validation (T009-T015)
4. **STOP and VALIDATE**: SC-001 passes? LiqPx baseline measured?
5. If yes → proceed to Phase 4 (US4: Solver V1.1)

### Full Delivery

1. Phases 1-4: P1 stories (US1 + US4) — core value
2. Phases 5-6: P2 stories (US2 + US3) — portfolio margin (`US2` complete; `US3` now has live PM examples available for validation)
3. Phase 7: Polish and final reports

### Key Risks

1. **US4 reserved-margin estimate is still best-effort**: The true formula is undocumented. Candidate B remains the empirical winner among scalar A-D candidates (`70.09%` overall), but the stronger operational heuristic is now Candidate E (`0.1 * max(buy_side_mmr, sell_side_mmr)` per coin). The latest healthy-chain rerun on 2026-03-31 restored `cross_margin tolerance_rate = 1.0000`, but V1.1 still has mixed liqPx effects globally (`217/325` improved, `108/325` worsened), so the reserved-margin path should still be treated as an empirical heuristic rather than a closed-form exchange match.
2. **US3 live sample remains narrow**: the PM solver validates within tolerance for the only currently comparable live PM account (`0xb1c4...` at `0.13%` error on the latest rerun), while the other observed PM accounts remain non-comparable. This is now an evidence/coverage monitor captured in `review_package.json`, not a repo implementation blocker.
3. **Operational dependency on local `/info`**: the local consensus node's `/info` endpoint is currently unstable, so live validation should use the VPS/public fallback chain until the node team completes stabilization.

---

## Notes

- **Research confirmed**: Cross-margin MMR validation now depends on live tier tables plus inferred maintenance deductions, not the old flat `notional / (2 * maxLeverage)` shortcut
- **Reserved margin is hidden**: API does not expose it in `clearinghouseState` — must be estimated from exposure bounds
- **Comparison target**: Use `crossMaintenanceMarginUsed` (MMR), NOT `totalMarginUsed` (IM)
- **Fair comparison**: Always use API-reported positions + mark prices for MMR computation (same-instant), NOT ABCI snapshot data
- **LiquidationPx available**: Per-position from same API call — validates solver directly
- **Multi-tier correction**: Only needed for whale accounts with 100+ positions at extreme notionals
- **Rate limit**: Conservative 10 req/min sufficient. `--detect-modes` bounded to top 50 accounts.
- **`_get_margin_tier` refactoring**: Extracted to `margin_math.py` standalone function (T004) to avoid validator depending on `SidecarPositionReconstructor` instance
