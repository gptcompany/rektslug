"""Tests for MarginValidator."""
import pytest
from unittest.mock import AsyncMock

from src.liquidationheatmap.hyperliquid.margin_validator import MarginValidator
from src.liquidationheatmap.hyperliquid.models import MarginValidationResult, MarginMode


@pytest.mark.asyncio
async def test_validate_user_mmr_within_tolerance():
    mock_client = AsyncMock()
    mock_client.get_clearinghouse_state.return_value = {
        "crossMaintenanceMarginUsed": "100.0",
        "marginSummary": {"accountValue": "1000.0", "totalMarginUsed": "200.0", "totalNtlPos": "0", "totalRawUsd": "0"},
        "crossMarginSummary": {"accountValue": "1000.0", "totalMarginUsed": "200.0", "totalNtlPos": "0", "totalRawUsd": "0"},
        "withdrawable": "800.0",
        "time": 1234567890,
        "assetPositions": [
            {
                "type": "oneWay",
                "position": {
                    "coin": "ETH", "szi": "1.0", "entryPx": "2000.0", "positionValue": "2000.0",
                    "unrealizedPnl": "0.0", "returnOnEquity": "0.0", "liquidationPx": "1800.0",
                    "leverage": {"type": "cross", "value": 20}, "marginUsed": "100.0",
                    "maxLeverage": 50, "cumFunding": {"allTime": "0", "sinceOpen": "0", "sinceChange": "0"}
                }
            }
        ]
    }
    mock_client.get_asset_meta.return_value = [
        {"universe": [{"name": "ETH", "szDecimals": 4, "maxLeverage": 50, "onlyIsolated": False}]},
        [{"markPx": "2000.0"}]
    ]
    
    validator = MarginValidator(client=mock_client)
    result = await validator.validate_user("0x123")
    
    assert isinstance(result, MarginValidationResult)
    assert result.user == "0x123"
    assert result.api_cross_maintenance_margin_used == 100.0
    assert result.deviation_mmr_pct is not None


@pytest.mark.asyncio
async def test_validate_user_liq_px_comparison():
    mock_client = AsyncMock()
    # Simplified mock for liq px testing
    mock_client.get_clearinghouse_state.return_value = {
        "crossMaintenanceMarginUsed": "100.0",
        "marginSummary": {"accountValue": "1000.0", "totalMarginUsed": "200.0", "totalNtlPos": "0", "totalRawUsd": "0"},
        "crossMarginSummary": {"accountValue": "1000.0", "totalMarginUsed": "200.0", "totalNtlPos": "0", "totalRawUsd": "0"},
        "withdrawable": "800.0",
        "time": 1234567890,
        "assetPositions": [
            {
                "type": "oneWay",
                "position": {
                    "coin": "ETH", "szi": "1.0", "entryPx": "2000.0", "positionValue": "2000.0",
                    "unrealizedPnl": "0.0", "returnOnEquity": "0.0", "liquidationPx": "1800.0",
                    "leverage": {"type": "cross", "value": 20}, "marginUsed": "100.0",
                    "maxLeverage": 50, "cumFunding": {"allTime": "0", "sinceOpen": "0", "sinceChange": "0"}
                }
            }
        ]
    }
    mock_client.get_asset_meta.return_value = [
        {"universe": [{"name": "ETH", "szDecimals": 4, "maxLeverage": 50, "onlyIsolated": False}]},
        [{"markPx": "2000.0"}]
    ]
    
    validator = MarginValidator(client=mock_client)
    result = await validator.validate_user("0x123")
    
    assert len(result.positions) == 1
    assert result.positions[0].api_liquidation_px == 1800.0


@pytest.mark.asyncio
async def test_validate_batch_report():
    mock_client = AsyncMock()
    validator = MarginValidator(client=mock_client)
    
    validator.validate_user = AsyncMock()
    validator.validate_user.return_value = MarginValidationResult(
        user="0x123", mode=MarginMode.CROSS_MARGIN, api_total_margin_used=200.0,
        api_cross_maintenance_margin_used=100.0, sidecar_total_mmr=100.0,
        deviation_mmr_pct=0.0, positions=[]
    )
    
    report = await validator.validate_batch(["0x123"])
    assert report.users_analyzed == 1
    assert report.mean_mmr_deviation_pct == 0.0

def test_detect_margin_mode_cross():
    validator = MarginValidator()
    state = {"assetPositions": [{"position": {"leverage": {"type": "cross"}}}]}
    assert validator.detect_margin_mode(state) == MarginMode.CROSS_MARGIN

def test_detect_margin_mode_isolated():
    validator = MarginValidator()
    state = {"assetPositions": [{"position": {"leverage": {"type": "isolated"}}}]}
    assert validator.detect_margin_mode(state) == MarginMode.ISOLATED_MARGIN

def test_detect_margin_mode_portfolio():
    validator = MarginValidator()
    # Mock PM structure based on docs
    state = {
        "portfolioMarginSummary": {"accountValue": "100", "portfolioMarginRatio": "0.5"},
        "assetPositions": [{"position": {"leverage": {"type": "cross"}}}]
    }
    assert validator.detect_margin_mode(state) == MarginMode.PORTFOLIO_MARGIN
