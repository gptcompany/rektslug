"""Data Transfer Objects (DTOs) for Hyperliquid API responses and validation."""

from dataclasses import dataclass
from enum import StrEnum


class MarginMode(StrEnum):
    """Detected margin mode for an account."""
    CROSS_MARGIN = "cross_margin"
    ISOLATED_MARGIN = "isolated_margin"
    PORTFOLIO_MARGIN = "portfolio_margin"


@dataclass(frozen=True)
class MarginSummary:
    accountValue: float
    totalMarginUsed: float
    totalNtlPos: float
    totalRawUsd: float


@dataclass(frozen=True)
class CrossMarginSummary:
    accountValue: float
    totalMarginUsed: float
    totalNtlPos: float
    totalRawUsd: float


@dataclass(frozen=True)
class PortfolioMarginSummary:
    accountValue: float
    totalMarginUsed: float
    totalNtlPos: float
    totalRawUsd: float
    portfolioMarginRatio: float


@dataclass(frozen=True)
class Leverage:
    type: str
    value: int


@dataclass(frozen=True)
class PositionCumFunding:
    allTime: float
    sinceOpen: float
    sinceChange: float


@dataclass(frozen=True)
class PositionData:
    coin: str
    szi: float
    entryPx: float
    positionValue: float
    unrealizedPnl: float
    returnOnEquity: float
    liquidationPx: float | None
    leverage: Leverage
    marginUsed: float
    maxLeverage: int
    cumFunding: PositionCumFunding


@dataclass(frozen=True)
class ApiPosition:
    type: str
    position: PositionData


@dataclass(frozen=True)
class ClearinghouseUserState:
    marginSummary: MarginSummary
    crossMarginSummary: CrossMarginSummary
    crossMaintenanceMarginUsed: float
    withdrawable: float
    assetPositions: list[ApiPosition]
    time: int
    portfolioMarginSummary: PortfolioMarginSummary | None = None


@dataclass(frozen=True)
class AssetMeta:
    name: str
    szDecimals: int
    maxLeverage: int
    onlyIsolated: bool


@dataclass(frozen=True)
class MarginTier:
    lower_bound: float
    mmr_rate: float
    maintenance_deduction: float


@dataclass(frozen=True)
class PositionMarginComparison:
    coin: str
    size: float
    entry_px: float
    mark_px: float
    api_margin_used: float  # IM from API
    api_liquidation_px: float | None
    sidecar_mmr: float
    sidecar_liquidation_px_v1: float | None
    sidecar_liquidation_px_v1_1: float | None
    deviation_liq_px_v1: float | None
    deviation_liq_px_v1_1: float | None


@dataclass(frozen=True)
class MarginValidationResult:
    user: str
    mode: MarginMode
    api_total_margin_used: float
    api_cross_maintenance_margin_used: float
    sidecar_total_mmr: float
    deviation_mmr_pct: float
    positions: list[PositionMarginComparison]
    best_candidate: str | None = None


@dataclass(frozen=True)
class MarginValidationReport:
    timestamp: str
    users_analyzed: int
    mean_mmr_deviation_pct: float
    results: list[MarginValidationResult]
