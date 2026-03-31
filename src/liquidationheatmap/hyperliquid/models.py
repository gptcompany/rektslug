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
    marginTableId: int

    @classmethod
    def from_api(cls, payload: dict) -> "AssetMeta":
        return cls(
            name=str(payload["name"]),
            szDecimals=int(payload.get("szDecimals", 0)),
            maxLeverage=int(payload.get("maxLeverage", 0)),
            onlyIsolated=bool(payload.get("onlyIsolated", False)),
            marginTableId=int(payload.get("marginTableId", 0)),
        )


@dataclass(frozen=True)
class AssetContext:
    markPx: float

    @classmethod
    def from_api(cls, payload: dict) -> "AssetContext":
        return cls(markPx=float(payload.get("markPx", 0.0)))


@dataclass(frozen=True)
class MarginTier:
    lower_bound: float
    mmr_rate: float
    maintenance_deduction: float


@dataclass(frozen=True)
class AssetMetaSnapshot:
    universe: list[AssetMeta] = field(default_factory=list)
    assetContexts: list[AssetContext] = field(default_factory=list)
    margin_tables: dict[int, list[MarginTier]] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: list) -> "AssetMetaSnapshot":
        meta = payload[0] if payload else {}
        universe_raw = meta.get("universe", [])
        asset_contexts = payload[1] if len(payload) > 1 else []

        margin_tables_raw = meta.get("marginTableIdToMarginTable")
        if margin_tables_raw is None:
            margin_tables_raw = meta.get("marginTables", [])
        margin_tables = {}
        for item in margin_tables_raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            table_id, table_data = item[0], item[1]
            if not isinstance(table_data, dict):
                continue

            tiers_raw = table_data.get("margin_tiers")
            lower_bound_scale = 1e6
            if tiers_raw is None:
                tiers_raw = table_data.get("marginTiers", [])
                lower_bound_scale = 1.0

            parsed_tiers_with_explicit = []
            for t in tiers_raw:
                if not isinstance(t, dict):
                    continue

                max_lev = float(t.get("max_leverage", t.get("maxLeverage", 50)))
                lower_bound_raw = float(t.get("lower_bound", t.get("lowerBound", 0)))
                maintenance_deduction_key = (
                    "maintenance_deduction"
                    if "maintenance_deduction" in t
                    else "maintenanceDeduction"
                )
                maintenance_deduction_raw = float(t.get(maintenance_deduction_key, 0))
                parsed_tiers_with_explicit.append(
                    (
                        lower_bound_raw / lower_bound_scale,
                        1.0 / (2.0 * max_lev) if max_lev > 0 else 0.01,
                        maintenance_deduction_raw / lower_bound_scale,
                        maintenance_deduction_key in t,
                    )
                )

            parsed_tiers_with_explicit.sort(key=lambda x: x[0])
            parsed_tiers = []
            previous_rate = 0.0
            previous_deduction = 0.0
            for lower_bound, mmr_rate, maintenance_deduction, has_explicit_deduction in parsed_tiers_with_explicit:
                if not has_explicit_deduction and parsed_tiers:
                    maintenance_deduction = previous_deduction + (
                        lower_bound * (mmr_rate - previous_rate)
                    )
                parsed_tiers.append(
                    MarginTier(
                        lower_bound=lower_bound,
                        mmr_rate=mmr_rate,
                        maintenance_deduction=maintenance_deduction,
                    )
                )
                previous_rate = mmr_rate
                previous_deduction = maintenance_deduction

            # Ensure tiers are sorted by lower_bound descending for lookup
            parsed_tiers.sort(key=lambda x: x.lower_bound, reverse=True)
            margin_tables[table_id] = parsed_tiers

        return cls(
            universe=[AssetMeta.from_api(item) for item in universe_raw],
            assetContexts=[AssetContext.from_api(item) for item in asset_contexts],
            margin_tables=margin_tables,
        )


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
