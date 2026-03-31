"""Extended tests for MarginValidator."""
import pytest
from unittest.mock import AsyncMock, patch
from src.liquidationheatmap.hyperliquid.margin_validator import MarginValidator
from src.liquidationheatmap.hyperliquid.models import (
    MarginMode, 
    AccountAbstraction, 
    ClearinghouseUserState,
    MarginSummary,
    CrossMarginSummary,
    ApiPosition,
    PositionData,
    PositionCumFunding,
    Leverage,
    AssetMetaSnapshot,
    AssetMeta,
    AssetContext,
    MarginValidationResult,
)

def make_simple_state(portfolio_margin_summary=None, asset_positions=None):
    return ClearinghouseUserState(
        marginSummary=MarginSummary(accountValue=1000.0, totalMarginUsed=200.0, totalNtlPos=0.0, totalRawUsd=0.0),
        crossMarginSummary=CrossMarginSummary(accountValue=1000.0, totalMarginUsed=200.0, totalNtlPos=0.0, totalRawUsd=0.0),
        crossMaintenanceMarginUsed=100.0,
        withdrawable=800.0,
        time=1234567890,
        portfolioMarginSummary=portfolio_margin_summary,
        assetPositions=asset_positions or [],
    )

def test_detect_margin_mode_raw_dict():
    validator = MarginValidator()
    
    # Portfolio Margin
    state = {"portfolioMarginSummary": {"something": 1}}
    assert validator.detect_margin_mode(state) == MarginMode.PORTFOLIO_MARGIN
    
    # Isolated Margin
    state = {
        "assetPositions": [
            {"position": {"leverage": {"type": "isolated"}}},
            {"position": {"leverage": {"type": "isolated"}}},
        ]
    }
    assert validator.detect_margin_mode(state) == MarginMode.ISOLATED_MARGIN
    
    # Cross Margin (default)
    state = {"assetPositions": []}
    assert validator.detect_margin_mode(state) == MarginMode.CROSS_MARGIN

@pytest.mark.asyncio
async def test_validate_user_no_positions():
    mock_client = AsyncMock()
    mock_client.get_clearinghouse_state.return_value = make_simple_state(asset_positions=[])
    mock_client.get_user_abstraction.return_value = AccountAbstraction.DEFAULT
    mock_client.get_asset_meta.return_value = AssetMetaSnapshot(universe=[], assetContexts=[], margin_tables={})
    
    validator = MarginValidator(client=mock_client)
    result = await validator.validate_user("0x123")
    
    assert result.user == "0x123"
    assert len(result.positions) == 0
    assert result.sidecar_total_mmr == 0.0
    assert result.deviation_mmr_pct == 100.0 # gap 100 / api 100

@pytest.mark.asyncio
async def test_validate_user_null_liq_px():
    mock_client = AsyncMock()
    pos = ApiPosition(
        type="oneWay",
        position=PositionData(
            coin="ETH", szi=1.0, entryPx=2000.0, positionValue=2000.0,
            unrealizedPnl=0.0, returnOnEquity=0.0,
            liquidationPx=None, # NULL
            leverage=Leverage(type="cross", value=20),
            marginUsed=100.0, maxLeverage=50,
            cumFunding=PositionCumFunding(allTime=0.0, sinceOpen=0.0, sinceChange=0.0),
        ),
    )
    mock_client.get_clearinghouse_state.return_value = make_simple_state(asset_positions=[pos])
    mock_client.get_user_abstraction.return_value = AccountAbstraction.DEFAULT
    mock_client.get_asset_meta.return_value = AssetMetaSnapshot(
        universe=[AssetMeta(name="ETH", szDecimals=4, maxLeverage=50, onlyIsolated=False, marginTableId=0)],
        assetContexts=[AssetContext(markPx=2000.0)],
        margin_tables={},
    )
    
    validator = MarginValidator(client=mock_client)
    result = await validator.validate_user("0x123")
    
    assert result.positions[0].api_liquidation_px is None
    assert result.positions[0].deviation_liq_px_v1 is None
    assert result.positions[0].liq_px_deviation_pct is None

@pytest.mark.asyncio
async def test_validate_user_pm_fetch_failure():
    mock_client = AsyncMock()
    mock_client.get_clearinghouse_state.return_value = make_simple_state()
    mock_client.get_user_abstraction.return_value = AccountAbstraction.PORTFOLIO_MARGIN
    mock_client.get_asset_meta.return_value = AssetMetaSnapshot(universe=[], assetContexts=[], margin_tables={})
    
    # This should fail when _compute_portfolio_margin_result is called
    mock_client.get_spot_clearinghouse_state.side_effect = Exception("PM Fetch Failed")
    
    validator = MarginValidator(client=mock_client)
    
    # validate_user itself doesn't catch the exception, it bubbles up
    with pytest.raises(Exception, match="PM Fetch Failed"):
        await validator.validate_user("0x123")

@pytest.mark.asyncio
async def test_validate_batch_continues_after_failure():
    mock_client = AsyncMock()
    # First user succeeds, second fails, third succeeds
    mock_client.get_clearinghouse_state.side_effect = [
        make_simple_state(),
        Exception("Failed!"),
        make_simple_state(),
    ]
    mock_client.get_user_abstraction.return_value = AccountAbstraction.DEFAULT
    mock_client.get_asset_meta.return_value = AssetMetaSnapshot(universe=[], assetContexts=[], margin_tables={})
    
    validator = MarginValidator(client=mock_client)
    report = await validator.validate_batch(["0x1", "0x2", "0x3"])
    
    assert report.users_analyzed == 2
    assert len(report.results) == 2
    assert report.results[0].user == "0x1"
    assert report.results[1].user == "0x3"


@pytest.mark.asyncio
async def test_validate_batch_reports_progress_for_success_and_failure():
    validator = MarginValidator(client=AsyncMock())
    validator.validate_user = AsyncMock(side_effect=[
        make_validation_result("0x1"),
        Exception("boom"),
        make_validation_result("0x3"),
    ])
    progress = []

    report = await validator.validate_batch(
        ["0x1", "0x2", "0x3"],
        progress_callback=lambda user, completed, total, success: progress.append(
            (user, completed, total, success)
        ),
    )

    assert report.users_analyzed == 2
    assert progress == [
        ("0x1", 1, 3, True),
        ("0x2", 2, 3, False),
        ("0x3", 3, 3, True),
    ]


def test_build_liq_px_summary_no_comparable_positions():
    validator = MarginValidator()
    # If all positions have deviation_liq_px_v1 as None
    summary = validator._build_liq_px_summary([])
    assert summary is None


def make_validation_result(user: str):
    return MarginValidationResult(
        user=user,
        mode=MarginMode.CROSS_MARGIN,
        account_abstraction="default",
        api_total_margin_used=200.0,
        api_cross_maintenance_margin_used=100.0,
        sidecar_total_mmr=100.0,
        deviation_mmr_pct=0.0,
        positions=[],
        factors=[],
        liq_px_summary=None,
    )
