"""Contract: Margin Validator.

Defines the interface for comparing sidecar margin calculations
against Hyperliquid API ground truth. Implementation goes in
src/liquidationheatmap/hyperliquid/margin_validator.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class MarginMode(StrEnum):
    CROSS_MARGIN = "cross_margin"
    PORTFOLIO_MARGIN = "portfolio_margin"
    ISOLATED_MARGIN = "isolated_margin"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PositionMarginComparison:
    coin: str
    api_margin_used: float
    sidecar_mmr: float
    api_liquidation_px: float | None
    sidecar_liquidation_px: float | None
    liq_px_deviation_pct: float | None
    position_size: float
    entry_px: float
    mark_px: float


@dataclass(frozen=True)
class FactorAttribution:
    resting_order_reserve: float
    funding_timing_delta: float
    fee_credit_estimate: float
    unknown_residual: float
    dominant_factor: str
    notes: str


@dataclass(frozen=True)
class MarginValidationResult:
    user_address: str
    margin_mode: MarginMode
    api_total_margin_used: float
    api_account_value: float
    sidecar_total_margin: float
    deviation_pct: float
    within_tolerance: bool  # deviation_pct <= 1.0
    positions: list[PositionMarginComparison]
    factor_attribution: FactorAttribution | None
    api_timestamp: str
    anchor_path: str


@dataclass(frozen=True)
class MarginValidationReport:
    metadata: dict
    user_count: int
    within_tolerance_count: int
    tolerance_rate: float
    passed: bool  # tolerance_rate >= 0.9
    results: list[MarginValidationResult]
    margin_mode_distribution: dict[str, int]
    factor_summary: dict[str, float]


class MarginValidator(Protocol):
    """Protocol for margin validation workflow."""

    async def validate_user(
        self,
        user_address: str,
        sidecar_state: object,  # UserState from sidecar
        mark_prices: dict[int, float],
        asset_margin_tiers: dict[int, list[dict]],
    ) -> MarginValidationResult:
        """Compare sidecar margin vs API for a single user."""
        ...

    async def validate_batch(
        self,
        user_addresses: list[str],
        anchor_path: str,
    ) -> MarginValidationReport:
        """Validate margin for a batch of users and produce aggregate report."""
        ...

    def detect_margin_mode(self, api_response: dict) -> MarginMode:
        """Classify account margin mode from raw API response."""
        ...

    def attribute_factors(
        self,
        result: MarginValidationResult,
        resting_orders: list[object],  # UserOrder from sidecar
    ) -> FactorAttribution:
        """Decompose margin deviation into identifiable factors."""
        ...
