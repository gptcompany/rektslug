"""Data Transfer Objects (DTOs) for Hyperliquid API responses and validation."""

from dataclasses import dataclass, field
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

    @classmethod
    def from_api(cls, payload: dict | None) -> "MarginSummary":
        data = payload or {}
        return cls(
            accountValue=float(data.get("accountValue", 0.0)),
            totalMarginUsed=float(data.get("totalMarginUsed", 0.0)),
            totalNtlPos=float(data.get("totalNtlPos", 0.0)),
            totalRawUsd=float(data.get("totalRawUsd", 0.0)),
        )


@dataclass(frozen=True)
class CrossMarginSummary:
    accountValue: float
    totalMarginUsed: float
    totalNtlPos: float
    totalRawUsd: float

    @classmethod
    def from_api(cls, payload: dict | None) -> "CrossMarginSummary":
        data = payload or {}
        return cls(
            accountValue=float(data.get("accountValue", 0.0)),
            totalMarginUsed=float(data.get("totalMarginUsed", 0.0)),
            totalNtlPos=float(data.get("totalNtlPos", 0.0)),
            totalRawUsd=float(data.get("totalRawUsd", 0.0)),
        )


@dataclass(frozen=True)
class PortfolioMarginSummary:
    accountValue: float
    totalMarginUsed: float
    totalNtlPos: float
    totalRawUsd: float
    portfolioMarginRatio: float

    @classmethod
    def from_api(cls, payload: dict | None) -> "PortfolioMarginSummary | None":
        if not payload:
            return None
        return cls(
            accountValue=float(payload.get("accountValue", 0.0)),
            totalMarginUsed=float(payload.get("totalMarginUsed", 0.0)),
            totalNtlPos=float(payload.get("totalNtlPos", 0.0)),
            totalRawUsd=float(payload.get("totalRawUsd", 0.0)),
            portfolioMarginRatio=float(payload.get("portfolioMarginRatio", 0.0)),
        )


@dataclass(frozen=True)
class Leverage:
    type: str
    value: int

    @classmethod
    def from_api(cls, payload: dict | None) -> "Leverage":
        data = payload or {}
        return cls(type=str(data.get("type", "cross")), value=int(data.get("value", 0)))


@dataclass(frozen=True)
class PositionCumFunding:
    allTime: float
    sinceOpen: float
    sinceChange: float

    @classmethod
    def from_api(cls, payload: dict | None) -> "PositionCumFunding":
        data = payload or {}
        return cls(
            allTime=float(data.get("allTime", 0.0)),
            sinceOpen=float(data.get("sinceOpen", 0.0)),
            sinceChange=float(data.get("sinceChange", 0.0)),
        )


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

    @classmethod
    def from_api(cls, payload: dict) -> "PositionData":
        liq_px = payload.get("liquidationPx")
        return cls(
            coin=str(payload["coin"]),
            szi=float(payload.get("szi", 0.0)),
            entryPx=float(payload.get("entryPx", 0.0)),
            positionValue=float(payload.get("positionValue", 0.0)),
            unrealizedPnl=float(payload.get("unrealizedPnl", 0.0)),
            returnOnEquity=float(payload.get("returnOnEquity", 0.0)),
            liquidationPx=float(liq_px) if liq_px not in (None, "") else None,
            leverage=Leverage.from_api(payload.get("leverage")),
            marginUsed=float(payload.get("marginUsed", 0.0)),
            maxLeverage=int(payload.get("maxLeverage", 0)),
            cumFunding=PositionCumFunding.from_api(payload.get("cumFunding")),
        )


@dataclass(frozen=True)
class ApiPosition:
    type: str
    position: PositionData

    @classmethod
    def from_api(cls, payload: dict) -> "ApiPosition":
        return cls(
            type=str(payload.get("type", "oneWay")),
            position=PositionData.from_api(payload.get("position", {})),
        )


@dataclass(frozen=True)
class ClearinghouseUserState:
    marginSummary: MarginSummary
    crossMarginSummary: CrossMarginSummary
    crossMaintenanceMarginUsed: float
    withdrawable: float
    assetPositions: list[ApiPosition]
    time: int
    portfolioMarginSummary: PortfolioMarginSummary | None = None

    @classmethod
    def from_api(cls, payload: dict) -> "ClearinghouseUserState":
        return cls(
            marginSummary=MarginSummary.from_api(payload.get("marginSummary")),
            crossMarginSummary=CrossMarginSummary.from_api(payload.get("crossMarginSummary")),
            crossMaintenanceMarginUsed=float(payload.get("crossMaintenanceMarginUsed", 0.0)),
            withdrawable=float(payload.get("withdrawable", 0.0)),
            assetPositions=[ApiPosition.from_api(item) for item in payload.get("assetPositions", [])],
            time=int(payload.get("time", 0)),
            portfolioMarginSummary=PortfolioMarginSummary.from_api(payload.get("portfolioMarginSummary")),
        )


@dataclass(frozen=True)
class AssetMeta:
    name: str
    szDecimals: int
    maxLeverage: int
    onlyIsolated: bool

    @classmethod
    def from_api(cls, payload: dict) -> "AssetMeta":
        return cls(
            name=str(payload["name"]),
            szDecimals=int(payload.get("szDecimals", 0)),
            maxLeverage=int(payload.get("maxLeverage", 0)),
            onlyIsolated=bool(payload.get("onlyIsolated", False)),
        )


@dataclass(frozen=True)
class AssetContext:
    markPx: float

    @classmethod
    def from_api(cls, payload: dict) -> "AssetContext":
        return cls(markPx=float(payload.get("markPx", 0.0)))


@dataclass(frozen=True)
class AssetMetaSnapshot:
    universe: list[AssetMeta] = field(default_factory=list)
    assetContexts: list[AssetContext] = field(default_factory=list)

    @classmethod
    def from_api(cls, payload: list) -> "AssetMetaSnapshot":
        universe = payload[0].get("universe", []) if payload else []
        asset_contexts = payload[1] if len(payload) > 1 else []
        return cls(
            universe=[AssetMeta.from_api(item) for item in universe],
            assetContexts=[AssetContext.from_api(item) for item in asset_contexts],
        )


@dataclass(frozen=True)
class MarginTier:
    lower_bound: float
    mmr_rate: float
    maintenance_deduction: float


@dataclass(frozen=True)
class FactorAttribution:
    category: str  # e.g., "multi_tier_rounding", "funding_timing", "estimated_resting_order_reserve", "unknown"
    estimated_impact_usd: float
    description: str


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
    liq_px_deviation_pct: float | None = None


@dataclass(frozen=True)
class LiqPxComparisonSummary:
    positions_compared: int
    improved_positions: int
    worsened_positions: int
    unchanged_positions: int
    v1_mean_abs_error: float | None = None
    v1_1_mean_abs_error: float | None = None
    improvement_rate: float | None = None


@dataclass(frozen=True)
class MarginModeReportSummary:
    users_analyzed: int
    tolerance_rate: float
    mean_mmr_deviation_pct: float
    liq_px_summary: LiqPxComparisonSummary | None = None


@dataclass(frozen=True)
class MarginValidationResult:
    user: str
    mode: MarginMode
    api_total_margin_used: float
    api_cross_maintenance_margin_used: float
    sidecar_total_mmr: float
    deviation_mmr_pct: float
    positions: list[PositionMarginComparison]
    factors: list[FactorAttribution] | None = None
    liq_px_summary: LiqPxComparisonSummary | None = None


@dataclass(frozen=True)
class MarginValidationReport:
    timestamp: str
    users_analyzed: int
    tolerance_rate: float
    mean_mmr_deviation_pct: float
    margin_mode_distribution: dict[str, int]
    mode_summaries: dict[str, MarginModeReportSummary]
    results: list[MarginValidationResult]
    liq_px_summary: LiqPxComparisonSummary | None = None
