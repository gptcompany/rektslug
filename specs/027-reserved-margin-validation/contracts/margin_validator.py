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


@dataclass(frozen=True)
class PositionMarginComparison:
    coin: str
    size: float
    entry_px: float
    mark_px: float
    api_margin_used: float
    api_liquidation_px: float | None
    sidecar_mmr: float
    sidecar_liquidation_px_v1: float | None
    sidecar_liquidation_px_v1_1: float | None
    deviation_liq_px_v1: float | None
    deviation_liq_px_v1_1: float | None
    liq_px_deviation_pct: float | None


@dataclass(frozen=True)
class FactorAttribution:
    category: str
    estimated_impact_usd: float
    description: str


@dataclass(frozen=True)
class LiqPxComparisonSummary:
    positions_compared: int
    improved_positions: int
    worsened_positions: int
    unchanged_positions: int
    v1_mean_abs_error: float | None
    v1_1_mean_abs_error: float | None
    improvement_rate: float | None


@dataclass(frozen=True)
class MarginValidationResult:
    user: str
    mode: MarginMode
    api_total_margin_used: float
    api_cross_maintenance_margin_used: float
    sidecar_total_mmr: float
    deviation_mmr_pct: float
    positions: list[PositionMarginComparison]
    factors: list[FactorAttribution] | None
    liq_px_summary: LiqPxComparisonSummary | None


@dataclass(frozen=True)
class MarginModeReportSummary:
    users_analyzed: int
    tolerance_rate: float
    mean_mmr_deviation_pct: float
    liq_px_summary: LiqPxComparisonSummary | None


@dataclass(frozen=True)
class MarginValidationReport:
    timestamp: str
    users_analyzed: int
    tolerance_rate: float
    mean_mmr_deviation_pct: float
    margin_mode_distribution: dict[str, int]
    mode_summaries: dict[str, MarginModeReportSummary]
    results: list[MarginValidationResult]
    liq_px_summary: LiqPxComparisonSummary | None


class MarginValidator(Protocol):
    """Protocol for margin validation workflow."""

    async def validate_user(self, user_address: str) -> MarginValidationResult:
        """Compare sidecar margin vs API for a single user."""
        ...

    async def validate_batch(self, user_addresses: list[str]) -> MarginValidationReport:
        """Validate margin for a batch of users and produce aggregate report."""
        ...

    def detect_margin_mode(self, api_response: object) -> MarginMode:
        """Classify account margin mode from parsed user state or raw API response."""
        ...

    def attribute_factors(self, deviation_pct: float, gap_usd: float) -> list[FactorAttribution]:
        """Decompose margin deviation into identifiable factor categories."""
        ...
