# Data Model: Reserved-Margin Validation & Portfolio-Margin Solver

**Date**: 2026-03-24 | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Entities

### MarginValidationResult

Per-user comparison of sidecar-calculated margin vs Hyperliquid API-reported margin.

| Field | Type | Description |
|-------|------|-------------|
| `user_address` | `str` | Ethereum address (0x-prefixed, lowercase) |
| `margin_mode` | `MarginMode` | Detected margin mode from API |
| `api_total_margin_used` | `float` | From `marginSummary.totalMarginUsed` |
| `api_account_value` | `float` | From `marginSummary.accountValue` |
| `sidecar_total_margin` | `float` | Sidecar-computed total margin (MMR + reserved) |
| `deviation_pct` | `float` | `abs(api - sidecar) / api * 100` |
| `within_tolerance` | `bool` | `deviation_pct <= 1.0` |
| `positions` | `list[PositionMarginComparison]` | Per-position breakdown |
| `factor_attribution` | `FactorAttribution | None` | If deviation > 1%, decomposition of gap |
| `api_timestamp` | `datetime` | When API was queried |
| `anchor_path` | `str` | ABCI snapshot used for sidecar computation |

### PositionMarginComparison

Per-position margin comparison within a user's account.

| Field | Type | Description |
|-------|------|-------------|
| `coin` | `str` | Asset symbol (e.g., "ETH", "BTC") |
| `api_margin_used` | `float` | From API per-position `marginUsed` |
| `sidecar_mmr` | `float` | Sidecar maintenance margin requirement |
| `api_liquidation_px` | `float` | From API `liquidationPx` |
| `sidecar_liquidation_px` | `float | None` | Sidecar-computed liquidation price |
| `liq_px_deviation_pct` | `float` | Deviation on liquidation price |
| `position_size` | `float` | Position size in base asset |
| `entry_px` | `float` | Entry price |
| `mark_px` | `float` | Mark price at validation time |

### MarginMode (Enum)

Account margin mode classification.

| Value | Description |
|-------|-------------|
| `CROSS_MARGIN` | Standard cross-margin (default) |
| `PORTFOLIO_MARGIN` | Portfolio margin with net risk netting |
| `ISOLATED_MARGIN` | Per-position isolated margin |
| `UNKNOWN` | Could not determine from API response |

### FactorAttribution

Decomposition of margin deviation for users exceeding 1% tolerance.

| Field | Type | Description |
|-------|------|-------------|
| `resting_order_reserve` | `float` | Estimated margin reserved for open orders |
| `funding_timing_delta` | `float` | Funding rate timing difference |
| `fee_credit_estimate` | `float` | Estimated fee credits / rebates |
| `unknown_residual` | `float` | Unexplained gap after attribution |
| `dominant_factor` | `str` | Which factor explains the most deviation |
| `notes` | `str` | Free-text explanation |

### ReservedMarginFormula

Parameterized formula for computing margin reserved by resting orders.

| Field | Type | Description |
|-------|------|-------------|
| `version` | `str` | Formula version (e.g., "v1.0") |
| `description` | `str` | Human-readable formula description |
| `order_types_covered` | `list[str]` | Which order types this formula handles |
| `compute` | `Callable` | `(orders, mark_prices, tiers) -> float` |

### PortfolioMarginState

State for portfolio-margin solver.

| Field | Type | Description |
|-------|------|-------------|
| `user_address` | `str` | Account address |
| `positions` | `list[UserPosition]` | All active positions |
| `net_exposure` | `dict[str, float]` | Net exposure per asset after netting |
| `portfolio_margin_ratio` | `float` | PMR from API (liquidation if > 0.95) |
| `total_margin_required` | `float` | Computed margin after netting |
| `is_liquidatable` | `bool` | `portfolio_margin_ratio > 0.95` |

### MarginValidationReport

Aggregate report across all validated users.

| Field | Type | Description |
|-------|------|-------------|
| `metadata` | `dict` | Run parameters, timestamp, anchor path |
| `user_count` | `int` | Number of users validated |
| `within_tolerance_count` | `int` | Users within 1% tolerance |
| `tolerance_rate` | `float` | `within_tolerance_count / user_count` |
| `pass` | `bool` | `tolerance_rate >= 0.9` (SC-001) |
| `results` | `list[MarginValidationResult]` | Per-user results |
| `margin_mode_distribution` | `dict[MarginMode, int]` | Mode counts |
| `factor_summary` | `dict[str, float]` | Aggregate factor attribution |

## State Transitions

### Validation Workflow

```
PENDING -> QUERYING_API -> COMPARING -> ATTRIBUTING -> COMPLETE
                |                          |
                v                          v
           API_FAILED              ATTRIBUTION_PARTIAL
           (retry/skip)           (unknown_residual > 5%)
```

### Account Classification

```
API Response -> detect_margin_mode() -> CROSS_MARGIN | PORTFOLIO_MARGIN | ISOLATED_MARGIN
                                              |                |
                                              v                v
                                    cross_margin_solver   portfolio_margin_solver
```

## Relationships

- `MarginValidationResult` has many `PositionMarginComparison` (1:N per position)
- `MarginValidationResult` has optional `FactorAttribution` (1:0..1, only if deviation > 1%)
- `MarginValidationReport` has many `MarginValidationResult` (1:N per user)
- `UserState` (existing sidecar entity) feeds into `MarginValidationResult`
- `UserPosition` (existing sidecar entity) feeds into `PositionMarginComparison`

## Validation Rules

- `user_address` must be valid Ethereum address (0x + 40 hex chars)
- `deviation_pct` is always non-negative
- `within_tolerance` is deterministic: exactly `deviation_pct <= 1.0`
- `tolerance_rate >= 0.9` required for SC-001 pass
- `unknown_residual` exceeding 5% of total margin triggers SC-005 warning
- `portfolio_margin_ratio > 0.95` is the liquidation trigger (SC-002)
