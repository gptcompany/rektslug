"""Tests for MarginValidator."""
import pytest
from unittest.mock import AsyncMock, patch

from src.liquidationheatmap.hyperliquid.margin_validator import MarginValidator
from src.liquidationheatmap.hyperliquid.models import (
    ApiPosition,
    AssetContext,
    AssetMeta,
    AssetMetaSnapshot,
    ClearinghouseUserState,
    CrossMarginSummary,
    Leverage,
    LiqPxComparisonSummary,
    MarginMode,
    MarginSummary,
    MarginTier,
    MarginValidationReport,
    MarginValidationResult,
    PortfolioMarginSummary,
    PositionCumFunding,
    PositionData,
)
from src.liquidationheatmap.hyperliquid.sidecar import UserOrder


@pytest.mark.asyncio
async def test_validate_user_mmr_within_tolerance():
    mock_client = AsyncMock()
    mock_client.get_clearinghouse_state.return_value = make_state(cross_maintenance_margin_used=20.0)
    mock_client.get_asset_meta.return_value = make_asset_snapshot()
    
    validator = MarginValidator(client=mock_client)
    result = await validator.validate_user("0x123")
    
    assert isinstance(result, MarginValidationResult)
    assert result.user == "0x123"
    assert result.api_cross_maintenance_margin_used == 20.0
    assert result.deviation_mmr_pct is not None
    assert len(result.factors) == 0  # No factors if deviation is small


@pytest.mark.asyncio
async def test_validate_user_tiered_mmr():
    mock_client = AsyncMock()
    # Position of 10.0 ETH at 2000.0 mark = 20,000 notional.
    # Tier 1: 0-10,000 @ 2.5% MMR, 0 deduction.
    # Tier 2: 10,000+ @ 5.0% MMR, 250 deduction.
    # Expected MMR = 20,000 * 0.05 - 250 = 1000 - 250 = 750.
    mock_client.get_clearinghouse_state.return_value = make_state(
        cross_maintenance_margin_used=750.0,
        szi=10.0
    )
    mock_client.get_asset_meta.return_value = make_asset_snapshot(
        margin_tables={
            10: [
                MarginTier(lower_bound=10000.0, mmr_rate=0.05, maintenance_deduction=250.0),
                MarginTier(lower_bound=0.0, mmr_rate=0.025, maintenance_deduction=0.0),
            ]
        },
        margin_table_id=10
    )
    
    validator = MarginValidator(client=mock_client)
    result = await validator.validate_user("0x123")
    
    assert result.sidecar_total_mmr == 750.0
    assert result.deviation_mmr_pct == 0.0


@pytest.mark.asyncio
async def test_validate_user_liq_px_comparison():
    mock_client = AsyncMock()
    mock_client.get_clearinghouse_state.return_value = make_state(cross_maintenance_margin_used=100.0)
    mock_client.get_asset_meta.return_value = make_asset_snapshot()
    
    validator = MarginValidator(client=mock_client)
    
    with patch.object(validator.reconstructor, "solve_liquidation_price", return_value=1750.0):
        result = await validator.validate_user("0x123")
    
        assert len(result.positions) == 1
        assert result.positions[0].api_liquidation_px == 1800.0
        assert result.positions[0].sidecar_liquidation_px_v1 == 1750.0
        assert result.positions[0].deviation_liq_px_v1 == 50.0


@pytest.mark.asyncio
async def test_validate_user_computes_v1_1_when_orders_available():
    mock_client = AsyncMock()
    mock_client.get_clearinghouse_state.return_value = make_state(cross_maintenance_margin_used=100.0)
    mock_client.get_asset_meta.return_value = make_asset_snapshot()

    validator = MarginValidator(
        client=mock_client,
        orders_by_user={
            "0x123": [
                UserOrder(
                    user="0x123",
                    oid=1,
                    coin="ETH",
                    side="B",
                    limit_px=2000.0,
                    size=1.0,
                )
            ]
        },
    )

    with patch.object(
        validator.reconstructor,
        "solve_liquidation_price",
        side_effect=[1750.0, 1775.0],
    ):
        result = await validator.validate_user("0x123")

    assert result.positions[0].sidecar_liquidation_px_v1 == 1750.0
    assert result.positions[0].sidecar_liquidation_px_v1_1 == 1775.0
    assert result.positions[0].deviation_liq_px_v1_1 == 25.0
    assert result.liq_px_summary is not None
    assert result.liq_px_summary.positions_compared == 1
    assert result.liq_px_summary.improved_positions == 1
    assert result.liq_px_summary.v1_mean_abs_error == 50.0
    assert result.liq_px_summary.v1_1_mean_abs_error == 25.0


@pytest.mark.asyncio
async def test_validate_user_outside_tolerance_gets_attribution():
    mock_client = AsyncMock()
    validator = MarginValidator(client=mock_client)
    
    factors = validator.attribute_factors(deviation_pct=2.5, gap_usd=50.0)
    assert [factor.category for factor in factors] == [
        "funding_timing",
        "estimated_resting_order_reserve",
        "unknown",
    ]
    assert sum(factor.estimated_impact_usd for factor in factors) == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_validate_batch_report():
    mock_client = AsyncMock()
    validator = MarginValidator(client=mock_client)
    
    validator.validate_user = AsyncMock()
    validator.validate_user.side_effect = [
        MarginValidationResult(
            user="0x1", mode=MarginMode.CROSS_MARGIN, api_total_margin_used=200.0,
            api_cross_maintenance_margin_used=100.0, sidecar_total_mmr=100.0,
            deviation_mmr_pct=0.0, positions=[], factors=[], liq_px_summary=None
        ),
        MarginValidationResult(
            user="0x2", mode=MarginMode.CROSS_MARGIN, api_total_margin_used=200.0,
            api_cross_maintenance_margin_used=100.0, sidecar_total_mmr=105.0,
            deviation_mmr_pct=5.0, positions=[], factors=[], liq_px_summary=None
        )
    ]
    
    report = await validator.validate_batch(["0x1", "0x2"])
    assert isinstance(report, MarginValidationReport)
    assert report.users_analyzed == 2
    assert report.mean_mmr_deviation_pct == 2.5
    assert report.tolerance_rate == 0.5
    assert report.margin_mode_distribution == {"cross_margin": 2}
    assert report.liq_px_summary is None
    assert report.mode_summaries["cross_margin"].users_analyzed == 2
    assert report.mode_summaries["cross_margin"].tolerance_rate == 0.5


def test_detect_margin_mode_cross():
    validator = MarginValidator()
    state = make_state()
    assert validator.detect_margin_mode(state) == MarginMode.CROSS_MARGIN

def test_detect_margin_mode_isolated():
    validator = MarginValidator()
    state = make_state(leverage_type="isolated")
    assert validator.detect_margin_mode(state) == MarginMode.ISOLATED_MARGIN

def test_detect_margin_mode_portfolio():
    validator = MarginValidator()
    state = make_state(
        portfolio_margin_summary=PortfolioMarginSummary(
            accountValue=100.0,
            totalMarginUsed=10.0,
            totalNtlPos=20.0,
            totalRawUsd=0.0,
            portfolioMarginRatio=0.5,
        )
    )
    assert validator.detect_margin_mode(state) == MarginMode.PORTFOLIO_MARGIN


def make_state(
    cross_maintenance_margin_used: float = 100.0,
    leverage_type: str = "cross",
    portfolio_margin_summary: PortfolioMarginSummary | None = None,
    szi: float = 1.0,
) -> ClearinghouseUserState:
    return ClearinghouseUserState(
        marginSummary=MarginSummary(
            accountValue=1000.0,
            totalMarginUsed=200.0,
            totalNtlPos=0.0,
            totalRawUsd=0.0,
        ),
        crossMarginSummary=CrossMarginSummary(
            accountValue=1000.0,
            totalMarginUsed=200.0,
            totalNtlPos=0.0,
            totalRawUsd=0.0,
        ),
        crossMaintenanceMarginUsed=cross_maintenance_margin_used,
        withdrawable=800.0,
        time=1234567890,
        portfolioMarginSummary=portfolio_margin_summary,
        assetPositions=[
            ApiPosition(
                type="oneWay",
                position=PositionData(
                    coin="ETH",
                    szi=szi,
                    entryPx=2000.0,
                    positionValue=szi * 2000.0,
                    unrealizedPnl=0.0,
                    returnOnEquity=0.0,
                    liquidationPx=1800.0,
                    leverage=Leverage(type=leverage_type, value=20),
                    marginUsed=100.0,
                    maxLeverage=50,
                    cumFunding=PositionCumFunding(
                        allTime=0.0,
                        sinceOpen=0.0,
                        sinceChange=0.0,
                    ),
                ),
            )
        ],
    )


def make_asset_snapshot(
    margin_tables: dict[int, list[MarginTier]] | None = None,
    margin_table_id: int = 0
) -> AssetMetaSnapshot:
    return AssetMetaSnapshot(
        universe=[
            AssetMeta(
                name="ETH",
                szDecimals=4,
                maxLeverage=50,
                onlyIsolated=False,
                marginTableId=margin_table_id,
            )
        ],
        assetContexts=[AssetContext(markPx=2000.0)],
        margin_tables=margin_tables or {},
    )
