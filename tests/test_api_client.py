"""Tests for the Hyperliquid API client."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient
from src.liquidationheatmap.hyperliquid.models import (
    AssetMetaSnapshot,
    ClearinghouseUserState,
)

@pytest.mark.asyncio
async def test_get_clearinghouse_state_parses_cross_maintenance_margin():
    client = HyperliquidInfoClient()
    mock_response = {
        "crossMaintenanceMarginUsed": "100.0",
        "marginSummary": {
            "accountValue": "1000.0",
            "totalMarginUsed": "200.0",
            "totalNtlPos": "0",
            "totalRawUsd": "0",
        },
        "crossMarginSummary": {
            "accountValue": "1000.0",
            "totalMarginUsed": "200.0",
            "totalNtlPos": "0",
            "totalRawUsd": "0",
        },
        "withdrawable": "800.0",
        "assetPositions": [],
        "time": 1234567890,
    }
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
        mock_post.return_value.__aenter__.return_value.raise_for_status = MagicMock()
        
        result = await client.get_clearinghouse_state("0x123")

        assert isinstance(result, ClearinghouseUserState)
        assert result.crossMaintenanceMarginUsed == 100.0
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"type": "clearinghouseState", "user": "0x123"}

@pytest.mark.asyncio
async def test_get_clearinghouse_state_parses_liquidation_px():
    client = HyperliquidInfoClient()
    mock_response = {
        "marginSummary": {
            "accountValue": "1000.0",
            "totalMarginUsed": "200.0",
            "totalNtlPos": "0",
            "totalRawUsd": "0",
        },
        "crossMarginSummary": {
            "accountValue": "1000.0",
            "totalMarginUsed": "200.0",
            "totalNtlPos": "0",
            "totalRawUsd": "0",
        },
        "crossMaintenanceMarginUsed": "100.0",
        "withdrawable": "800.0",
        "assetPositions": [
            {
                "type": "oneWay",
                "position": {
                    "coin": "ETH",
                    "szi": "1.0",
                    "entryPx": "2000.0",
                    "positionValue": "2000.0",
                    "unrealizedPnl": "0.0",
                    "returnOnEquity": "0.0",
                    "liquidationPx": "1800.0",
                    "leverage": {"type": "cross", "value": 20},
                    "marginUsed": "100.0",
                    "maxLeverage": 50,
                    "cumFunding": {"allTime": "0.0", "sinceOpen": "0.0", "sinceChange": "0.0"},
                },
            }
        ],
        "time": 1234567890,
    }
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
        mock_post.return_value.__aenter__.return_value.raise_for_status = MagicMock()
        
        result = await client.get_clearinghouse_state("0x123")

        assert result.assetPositions[0].position.liquidationPx == 1800.0

@pytest.mark.asyncio
async def test_get_clearinghouse_state_handles_timeout():
    client = HyperliquidInfoClient()
    client.rate_limit_delay = 0.0  # speed up test
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.side_effect = asyncio.TimeoutError("Timeout!")
        
        with pytest.raises(asyncio.TimeoutError):
            await client.get_clearinghouse_state("0x123")
        
        # It should retry 3 times
        assert mock_post.call_count == 3

@pytest.mark.asyncio
async def test_get_asset_meta_returns_tiers():
    client = HyperliquidInfoClient()
    mock_response = [
        {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 50, "onlyIsolated": False}]},
        [{"markPx": "50000.0"}],
    ]
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
        mock_post.return_value.__aenter__.return_value.raise_for_status = MagicMock()
        
        result = await client.get_asset_meta()

        assert isinstance(result, AssetMetaSnapshot)
        assert result.universe[0].name == "BTC"
        assert result.assetContexts[0].markPx == 50000.0
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"type": "metaAndAssetCtxs"}


@pytest.mark.asyncio
async def test_get_asset_meta_parses_live_margin_tables_format():
    client = HyperliquidInfoClient()
    mock_response = [
        {
            "universe": [
                {
                    "name": "BTC",
                    "szDecimals": 5,
                    "maxLeverage": 40,
                    "onlyIsolated": False,
                    "marginTableId": 56,
                }
            ],
            "marginTables": [
                [
                    56,
                    {
                        "description": "tiered 40x",
                        "marginTiers": [
                            {"lowerBound": "0.0", "maxLeverage": 40},
                            {"lowerBound": "150000000.0", "maxLeverage": 20},
                        ],
                    },
                ]
            ],
        },
        [{"markPx": "50000.0"}],
    ]

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
        mock_post.return_value.__aenter__.return_value.raise_for_status = MagicMock()

        result = await client.get_asset_meta()

    assert result.universe[0].marginTableId == 56
    assert 56 in result.margin_tables
    assert result.margin_tables[56][0].lower_bound == 150000000.0
    assert result.margin_tables[56][0].mmr_rate == 0.025
    assert result.margin_tables[56][0].maintenance_deduction == 1875000.0
    assert result.margin_tables[56][1].lower_bound == 0.0
    assert result.margin_tables[56][1].mmr_rate == 0.0125


@pytest.mark.asyncio
async def test_get_asset_meta_infers_piecewise_live_maintenance_deduction():
    client = HyperliquidInfoClient()
    mock_response = [
        {
            "universe": [
                {
                    "name": "BTC",
                    "szDecimals": 5,
                    "maxLeverage": 20,
                    "onlyIsolated": False,
                    "marginTableId": 99,
                }
            ],
            "marginTables": [
                [
                    99,
                    {
                        "description": "synthetic three-tier table",
                        "marginTiers": [
                            {"lowerBound": "0.0", "maxLeverage": 40},
                            {"lowerBound": "150000000.0", "maxLeverage": 20},
                            {"lowerBound": "300000000.0", "maxLeverage": 10},
                        ],
                    },
                ]
            ],
        },
        [{"markPx": "50000.0"}],
    ]

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
        mock_post.return_value.__aenter__.return_value.raise_for_status = MagicMock()

        result = await client.get_asset_meta()

    tiers = result.margin_tables[99]
    assert [tier.lower_bound for tier in tiers] == [300000000.0, 150000000.0, 0.0]
    assert [tier.mmr_rate for tier in tiers] == [0.05, 0.025, 0.0125]
    assert [tier.maintenance_deduction for tier in tiers] == [9375000.0, 1875000.0, 0.0]

@pytest.mark.asyncio
async def test_batch_query_returns_partial_on_failure():
    client = HyperliquidInfoClient()
    users = ["0x1", "0x2", "0x3"]
    state = ClearinghouseUserState(
        marginSummary=mock_margin_summary(),
        crossMarginSummary=mock_cross_margin_summary(),
        crossMaintenanceMarginUsed=10.0,
        withdrawable=0.0,
        assetPositions=[],
        time=1,
    )
    
    with patch.object(client, "get_clearinghouse_state", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [
            state,
            Exception("Failed!"),
            state,
        ]
        
        results = await client.get_clearinghouse_states_batch(users)
        
        assert len(results) == 2
        assert "0x1" in results
        assert "0x3" in results
        assert "0x2" not in results
        assert mock_get.call_count == 3


def mock_margin_summary():
    from src.liquidationheatmap.hyperliquid.models import MarginSummary

    return MarginSummary(
        accountValue=1000.0,
        totalMarginUsed=200.0,
        totalNtlPos=0.0,
        totalRawUsd=0.0,
    )


def mock_cross_margin_summary():
    from src.liquidationheatmap.hyperliquid.models import CrossMarginSummary

    return CrossMarginSummary(
        accountValue=1000.0,
        totalMarginUsed=200.0,
        totalNtlPos=0.0,
        totalRawUsd=0.0,
    )
