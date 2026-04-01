"""Tests for the Hyperliquid API client."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.liquidationheatmap.hyperliquid.api_client import (
    HyperliquidInfoClient,
    _EndpointPayloadUnsupportedError,
    _EndpointUnavailableError,
)
from src.liquidationheatmap.hyperliquid.models import (
    AccountAbstraction,
    AssetMetaSnapshot,
    BorrowLendReserveState,
    BorrowLendUserState,
    ClearinghouseUserState,
    SpotClearinghouseState,
)


def configure_json_response(mock_post: MagicMock, payload, *, status: int = 200):
    response = mock_post.return_value.__aenter__.return_value
    response.status = status
    response.text = AsyncMock(return_value=json.dumps(payload))
    response.raise_for_status = MagicMock()
    response.request_info = MagicMock()
    response.history = ()
    return response


def test_client_uses_public_info_api_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HEATMAP_HYPERLIQUID_INFO_FALLBACK_URLS", raising=False)
    monkeypatch.delenv("HYPERLIQUID_INFO_FALLBACK_URLS", raising=False)
    monkeypatch.delenv("HEATMAP_HYPERLIQUID_INFO_URL", raising=False)
    monkeypatch.delenv("HYPERLIQUID_INFO_URL", raising=False)

    client = HyperliquidInfoClient()

    assert client.base_url == HyperliquidInfoClient.DEFAULT_BASE_URL
    assert client.base_urls == [HyperliquidInfoClient.DEFAULT_BASE_URL]


def test_client_reads_base_url_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HEATMAP_HYPERLIQUID_INFO_FALLBACK_URLS", raising=False)
    monkeypatch.setenv("HEATMAP_HYPERLIQUID_INFO_URL", "http://localhost:3001/info")

    client = HyperliquidInfoClient()

    assert client.base_url == "http://localhost:3001/info"
    assert client.base_urls == ["http://localhost:3001/info"]


def test_client_reads_fallback_base_urls_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "HEATMAP_HYPERLIQUID_INFO_FALLBACK_URLS",
        "http://localhost:3001/info, http://10.0.0.1:3001/info, https://api.hyperliquid.xyz/info",
    )

    client = HyperliquidInfoClient()

    assert client.base_urls == [
        "http://localhost:3001/info",
        "http://10.0.0.1:3001/info",
        "https://api.hyperliquid.xyz/info",
    ]
    assert client.base_url == "http://localhost:3001/info"


def test_client_explicit_base_url_overrides_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "HEATMAP_HYPERLIQUID_INFO_FALLBACK_URLS",
        "http://localhost:3001/info, http://10.0.0.1:3001/info",
    )
    monkeypatch.setenv("HEATMAP_HYPERLIQUID_INFO_URL", "http://localhost:3001/info")

    client = HyperliquidInfoClient(base_url="http://127.0.0.1:3999/info")

    assert client.base_url == "http://127.0.0.1:3999/info"
    assert client.base_urls == ["http://127.0.0.1:3999/info"]


@pytest.mark.asyncio
async def test_post_falls_back_to_next_endpoint_when_primary_is_unavailable():
    client = HyperliquidInfoClient(
        base_urls=[
            "http://localhost:3001/info",
            "http://10.0.0.1:3001/info",
            "https://api.hyperliquid.xyz/info",
        ],
        endpoint_cooldown_seconds=120.0,
    )
    client.rate_limit_delay = 0.0

    with patch.object(
        client,
        "_post_to_base_url",
        side_effect=[
            _EndpointUnavailableError("local down"),
            {"ok": True},
        ],
    ) as mocked_post:
        result = await client._post({"type": "userAbstraction", "user": "0x123"})

    assert result == {"ok": True}
    assert [call.args[0] for call in mocked_post.call_args_list] == [
        "http://localhost:3001/info",
        "http://10.0.0.1:3001/info",
    ]
    assert client._endpoint_cooldown_until["http://localhost:3001/info"] > 0.0


@pytest.mark.asyncio
async def test_post_skips_endpoint_after_payload_marked_unsupported():
    client = HyperliquidInfoClient(
        base_urls=[
            "http://localhost:3001/info",
            "http://10.0.0.1:3001/info",
            "https://api.hyperliquid.xyz/info",
        ],
    )
    client.rate_limit_delay = 0.0

    with patch.object(
        client,
        "_post_to_base_url",
        side_effect=[
            _EndpointPayloadUnsupportedError("meta unsupported locally"),
            {"ok": "vps"},
            {"ok": "public"},
        ],
    ) as mocked_post:
        first = await client._post({"type": "metaAndAssetCtxs"})
        second = await client._post({"type": "metaAndAssetCtxs"})

    assert first == {"ok": "vps"}
    assert second == {"ok": "public"}
    assert [call.args[0] for call in mocked_post.call_args_list] == [
        "http://localhost:3001/info",
        "http://10.0.0.1:3001/info",
        "http://10.0.0.1:3001/info",
    ]
    assert (
        client._unsupported_payload_cooldown_until[
            ("http://localhost:3001/info", "metaAndAssetCtxs")
        ]
        > 0.0
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
        configure_json_response(mock_post, mock_response)
        
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
        configure_json_response(mock_post, mock_response)
        
        result = await client.get_clearinghouse_state("0x123")

        assert result.assetPositions[0].position.liquidationPx == 1800.0

@pytest.mark.asyncio
async def test_get_clearinghouse_state_handles_timeout():
    client = HyperliquidInfoClient(base_urls=["https://api.hyperliquid.xyz/info"])
    client.rate_limit_delay = 0.0  # speed up test
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.side_effect = asyncio.TimeoutError("Timeout!")
        
        with pytest.raises(_EndpointUnavailableError):
            await client.get_clearinghouse_state("0x123")
        
        # It should retry 3 times
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_get_user_abstraction_returns_enum():
    client = HyperliquidInfoClient()

    with patch("aiohttp.ClientSession.post") as mock_post:
        configure_json_response(mock_post, "portfolioMargin")

        result = await client.get_user_abstraction("0x123")

    assert result == AccountAbstraction.PORTFOLIO_MARGIN


@pytest.mark.asyncio
async def test_get_spot_clearinghouse_state_parses_balances():
    client = HyperliquidInfoClient()
    mock_response = {
        "balances": [
            {
                "coin": "USDC",
                "token": 0,
                "total": "100.5",
                "hold": "20.25",
                "entryNtl": "0.0",
            }
        ],
        "tokenToAvailableAfterMaintenance": [[0, "80.25"]],
    }

    with patch("aiohttp.ClientSession.post") as mock_post:
        configure_json_response(mock_post, mock_response)

        result = await client.get_spot_clearinghouse_state("0x123")

    assert isinstance(result, SpotClearinghouseState)
    assert result.balances[0].coin == "USDC"
    assert result.balances[0].hold == 20.25
    assert result.tokenToAvailableAfterMaintenance == [(0, 80.25)]


@pytest.mark.asyncio
async def test_get_borrow_lend_user_state_parses_token_states():
    client = HyperliquidInfoClient()
    mock_response = {
        "tokenToState": [
            [
                0,
                {
                    "borrow": {"basis": "1.5", "value": "2.5"},
                    "supply": {"basis": "3.5", "value": "4.5"},
                },
            ]
        ],
        "health": "healthy",
        "healthFactor": None,
    }

    with patch("aiohttp.ClientSession.post") as mock_post:
        configure_json_response(mock_post, mock_response)

        result = await client.get_borrow_lend_user_state("0x123")

    assert isinstance(result, BorrowLendUserState)
    assert result.health == "healthy"
    assert result.tokenToState[0].borrow.value == 2.5
    assert result.tokenToState[0].supply.value == 4.5


@pytest.mark.asyncio
async def test_get_all_borrow_lend_reserve_states_parses_map():
    client = HyperliquidInfoClient()
    mock_response = [
        [
            0,
            {
                "borrowYearlyRate": "0.05",
                "supplyYearlyRate": "0.01",
                "balance": "100.0",
                "utilization": "0.1",
                "oraclePx": "1.0",
                "ltv": "0.0",
                "totalSupplied": "200.0",
                "totalBorrowed": "20.0",
            },
        ]
    ]

    with patch("aiohttp.ClientSession.post") as mock_post:
        configure_json_response(mock_post, mock_response)

        result = await client.get_all_borrow_lend_reserve_states()

    assert result[0] == BorrowLendReserveState(
        borrowYearlyRate=0.05,
        supplyYearlyRate=0.01,
        balance=100.0,
        utilization=0.1,
        oraclePx=1.0,
        ltv=0.0,
        totalSupplied=200.0,
        totalBorrowed=20.0,
    )

@pytest.mark.asyncio
async def test_get_asset_meta_returns_tiers():
    client = HyperliquidInfoClient()
    mock_response = [
        {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 50, "onlyIsolated": False}]},
        [{"markPx": "50000.0"}],
    ]
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        configure_json_response(mock_post, mock_response)
        
        result = await client.get_asset_meta()

        assert isinstance(result, AssetMetaSnapshot)
        assert result.universe[0].name == "BTC"
        assert result.assetContexts[0].markPx == 50000.0
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"type": "metaAndAssetCtxs"}


@pytest.mark.asyncio
async def test_get_asset_meta_without_contexts_uses_meta_payload():
    client = HyperliquidInfoClient()
    mock_response = {
        "universe": [
            {"name": "BTC", "szDecimals": 5, "maxLeverage": 50, "onlyIsolated": False}
        ],
        "marginTables": [],
    }

    with patch("aiohttp.ClientSession.post") as mock_post:
        configure_json_response(mock_post, mock_response)

        result = await client.get_asset_meta(include_asset_contexts=False)

        assert isinstance(result, AssetMetaSnapshot)
        assert result.universe[0].name == "BTC"
        assert result.assetContexts == []
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"type": "meta"}


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
        configure_json_response(mock_post, mock_response)

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
        configure_json_response(mock_post, mock_response)

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


@pytest.mark.asyncio
async def test_borrow_lend_batch_query_returns_partial_on_failure():
    client = HyperliquidInfoClient()
    users = ["0x1", "0x2", "0x3"]
    borrow_lend_state = BorrowLendUserState(
        tokenToState={},
        health="healthy",
        healthFactor=1.5,
    )

    with patch.object(client, "get_borrow_lend_user_state", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [
            borrow_lend_state,
            Exception("Failed!"),
            borrow_lend_state,
        ]

        results = await client.get_borrow_lend_user_states_batch(users)

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
