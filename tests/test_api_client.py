"""Tests for the Hyperliquid API client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.liquidationheatmap.hyperliquid.api_client import HyperliquidInfoClient

@pytest.mark.asyncio
async def test_get_clearinghouse_state():
    client = HyperliquidInfoClient()
    mock_response = {"marginSummary": {"totalMarginUsed": "100.0"}}
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
        mock_post.return_value.__aenter__.return_value.raise_for_status = MagicMock()
        
        result = await client.get_clearinghouse_state("0x123")
        
        assert result == mock_response
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"type": "clearinghouseState", "user": "0x123"}

@pytest.mark.asyncio
async def test_get_asset_meta():
    client = HyperliquidInfoClient()
    mock_response = [{"universe": [{"name": "BTC", "maxLeverage": 50}]}]
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
        mock_post.return_value.__aenter__.return_value.raise_for_status = MagicMock()
        
        result = await client.get_asset_meta()
        
        assert result == mock_response
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"type": "metaAndAssetCtxs"}

@pytest.mark.asyncio
async def test_get_clearinghouse_states_batch():
    client = HyperliquidInfoClient()
    users = ["0x1", "0x2"]
    
    with patch.object(client, "get_clearinghouse_state", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [{"user": "0x1"}, {"user": "0x2"}]
        
        results = await client.get_clearinghouse_states_batch(users)
        
        assert len(results) == 2
        assert "0x1" in results
        assert "0x2" in results
        assert mock_get.call_count == 2
