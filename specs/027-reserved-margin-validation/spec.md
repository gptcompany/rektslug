# Feature Specification: Reserved-Margin Validation & Portfolio-Margin Solver

**Feature Branch**: `027-reserved-margin-validation`
**Created**: 2026-03-24
**Status**: Implemented
**Input**: Validate reserved-margin formula against Hyperliquid API and implement portfolio-margin solver
**Dependencies**: spec-026 (sidecar, solver V1, outlier artifacts in `data/validation/`)

**Implementation Note (2026-04-17)**: The repo now ships the reserved-margin validator, margin-mode detection/routing, portfolio-margin solver, and an offline review package at `specs/027-reserved-margin-validation/review_package.json`. The current observable PM universe still yields only one live-comparable `liquidationPx`; the retained package now checks coverage against the observed PM account artifacts and preserves non-comparable accounts explicitly.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reserved-Margin Formula Validation (Priority: P1)

As a liquidation-map developer, I need to validate my reserved-margin formula against the Hyperliquid clearinghouse API so that the sidecar's margin calculations match the exchange's actual accounting within 1% tolerance.

**Why this priority**: The reserved-margin formula is currently a black-box guess. Without validation, every downstream calculation (liquidation prices, risk surfaces) carries unknown systematic error. This is the highest-leverage investigation — it unblocks everything else.

**Independent Test**: Query `clearinghouseState` for 10+ outlier users identified in spec-026. Compare `marginUsed` and `totalMarginUsed` from the API response against the sidecar's calculated values. Pass if 90%+ of users are within 1%.

**Acceptance Scenarios**:

1. **Given** an outlier user from `hl_reserved_margin_outliers_eth_sample.json`, **When** I query Hyperliquid API `clearinghouseState` for that user, **Then** the API returns `marginSummary.totalMarginUsed` and per-position `marginUsed` values
2. **Given** API margin values for 10+ outlier users, **When** I compare against sidecar-calculated margin values, **Then** 90% or more of users show less than 1% deviation on `marginUsed`
3. **Given** a user where the margin gap exceeds 1%, **When** I decompose the delta, **Then** I can attribute it to identifiable factors (resting orders, fee credits, funding timing, or other documented causes)

---

### User Story 2 - Portfolio-Margin Account Detection (Priority: P2)

As a liquidation-map developer, I need to detect which accounts use Hyperliquid's portfolio-margin mode so that I can route them to the correct solver and avoid producing incorrect liquidation prices for institutional accounts.

**Why this priority**: Portfolio margin (alpha March 2026) uses fundamentally different liquidation semantics (net risk netting, `portfolio_margin_ratio`). Without detection, the cross-margin solver silently produces wrong results for these accounts.

**Independent Test**: Query a known set of high-volume accounts via API and classify them as standard cross-margin or portfolio-margin based on API response fields.

**Acceptance Scenarios**:

1. **Given** a Hyperliquid account in standard cross-margin mode, **When** I query its `clearinghouseState`, **Then** the response includes `crossMarginSummary` and does NOT include active `portfolioMarginSummary`
2. **Given** a Hyperliquid account in portfolio-margin mode, **When** I query its `clearinghouseState`, **Then** the response includes `portfolioMarginSummary` with `portfolioMarginRatio`
3. **Given** the sidecar processes a set of accounts, **When** it encounters a portfolio-margin account, **Then** it routes the account to the portfolio-margin solver (not the cross-margin solver)

---

### User Story 3 - Portfolio-Margin Solver (Priority: P2)

As a liquidation-map developer, I need a solver that correctly computes liquidation prices for portfolio-margin accounts using net-risk netting and the `portfolio_margin_ratio` threshold, so that institutional accounts appear at correct levels on the risk surface.

**Why this priority**: Same as US2 — portfolio-margin accounts have different liquidation triggers. The solver must handle both modes to produce a correct full-population risk surface.

**Independent Test**: Compute liquidation prices for the currently observable portfolio-margin account set retained in local artifacts, preserve comparable and non-comparable accounts in the review package, and verify that all comparable live `liquidationPx` values remain within 1%.

**Acceptance Scenarios**:

1. **Given** a portfolio-margin account with offsetting BTC long and ETH short, **When** the solver computes its margin requirement, **Then** the requirement reflects net risk reduction (lower than sum of individual position margins)
2. **Given** a portfolio-margin account, **When** its `portfolio_margin_ratio` exceeds 0.95, **Then** the solver correctly identifies it as liquidatable
3. **Given** portfolio-margin solver output for the retained observable PM account set, **When** compared against Hyperliquid API `liquidationPx`, **Then** every comparable live PM value is within 1% and every non-comparable observed PM account is preserved explicitly in the review package

---

### User Story 4 - Solver V1.1 with Correct Reserved-Margin (Priority: P1)

As a liquidation-map developer, I need to update the cross-margin solver to use the validated reserved-margin formula derived from API analysis, so that the sidecar produces accurate risk surfaces including the margin impact of resting orders.

**Why this priority**: The current solver V1 ignores reserved margin entirely. Even if the formula is approximately correct, integrating it improves every downstream artifact.

**Independent Test**: Generate an ETH 7d risk surface with solver V1.1 and compare shape, volume, and L/S ratio against V1 baseline. Validate margin values against API for sample users.

**Acceptance Scenarios**:

1. **Given** the validated reserved-margin formula, **When** integrated into the cross-margin solver, **Then** `totalMarginUsed` for sample users matches API within 1%
2. **Given** an account with significant resting orders, **When** the solver computes its liquidation price, **Then** the price shifts closer to API-reported `liquidationPx` compared to V1
3. **Given** solver V1.1 generating an ETH 7d surface, **When** compared to V1 output, **Then** the artifacts document which buckets shifted and why

---

### Edge Cases

- What happens when the API is rate-limited or returns incomplete data for some users?
- How does the solver handle accounts with both cross-margin and isolated-margin positions?
- What if a user switches from cross-margin to portfolio-margin between ABCI snapshots?
- How are accounts with zero resting orders handled? (expected: V1.1 matches V1 exactly)
- What if the reserved-margin formula differs between order types (limit vs stop-limit vs TP/SL)?
- How are strict-isolated assets handled differently from standard isolated?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST query Hyperliquid `clearinghouseState` API for specified user addresses and extract `marginSummary` and per-position margin fields
- **FR-002**: System MUST compare API-reported `marginUsed` against sidecar-calculated margin for each position and report the percentage deviation
- **FR-003**: System MUST decompose margin deviations exceeding 1% into identifiable factor categories (resting-order reserve, funding timing, fee credits, unknown)
- **FR-004**: System MUST detect whether an account operates in standard cross-margin, portfolio-margin, or isolated-margin mode based on API response structure
- **FR-005**: System MUST implement a portfolio-margin solver that computes liquidation conditions using net-risk netting and the `portfolio_margin_ratio > 0.95` threshold
- **FR-006**: System MUST route accounts to the correct solver (cross-margin or portfolio-margin) based on detected margin mode
- **FR-007**: System MUST update the cross-margin solver (V1 -> V1.1) to incorporate the validated reserved-margin formula
- **FR-008**: System MUST produce validation reports documenting margin deviations, factor attributions, and margin-mode distribution across the analyzed population
- **FR-009**: System MUST handle API failures gracefully (rate limits, timeouts) with retry logic and partial-result reporting

### Key Entities

- **MarginValidationReport**: Per-user comparison of sidecar vs API margin values, deviation %, factor attribution
- **MarginMode**: Classification {CrossMargin, PortfolioMargin, IsolatedMargin} — detected per account
- **ReservedMarginFormula**: The derived formula mapping resting orders to margin reserve, parameterized by order type, size, leverage tier
- **PortfolioMarginState**: Net risk calculation across positions, borrowed assets, supply caps, and `portfolio_margin_ratio`

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `marginUsed` calculated by sidecar matches Hyperliquid API within 1% for 90%+ of the 10+ validated outlier users
- **SC-002**: Portfolio-margin accounts are correctly detected and routed — 100% correct classification for tested accounts
- **SC-003**: Portfolio-margin solver produces `liquidationPx` within 1% of API values for all comparable accounts in the currently observable retained PM account set, and the review package explicitly records any observed but non-comparable PM accounts
- **SC-004**: Solver V1.1 risk-surface artifacts show documented, explainable changes vs V1 baseline (no unexplained regressions)
- **SC-005**: Validation report fully attributes or documents the margin gap for each analyzed user — zero "unknown" gaps exceeding 5% of total margin

## Scope Boundary

### In Scope
- API validation of reserved-margin formula
- Margin-mode detection (cross vs portfolio vs isolated)
- Portfolio-margin solver implementation
- Solver V1.1 with corrected reserved-margin
- Validation reports and artifacts

### Not In Scope
- Consumer checkpoint 7d persistence (spec-028)
- CoinGlass shape comparison (concluded in spec-026)
- Real-time / streaming margin updates
- UI / frontend visualization changes
- Production deployment or CI/CD integration

## Assumptions

- Hyperliquid `clearinghouseState` API endpoint remains stable and accessible without authentication for public addresses
- Portfolio-margin alpha is active and detectable via API response fields
- The 10+ outlier users from spec-026 artifacts are still active with positions on Hyperliquid
- Margin tier tables are accessible via the `meta` Info endpoint
- Rate limiting on the Info API allows at least 10-20 queries per minute
