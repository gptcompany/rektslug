"""Extended tests for HyperliquidInfoClient."""
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock

import aiohttp
import pytest
from src.liquidationheatmap.hyperliquid.api_client import (
    HyperliquidInfoClient,
    _EndpointUnavailableError,
    _EndpointPayloadUnsupportedError,
)

@pytest.mark.asyncio
async def test_candidate_base_urls_respects_cooldowns():
    client = HyperliquidInfoClient(
        base_urls=["http://a.com", "http://b.com", "http://c.com"],
        endpoint_cooldown_seconds=60.0,
    )
    
    now = time.monotonic()
    # a.com is in endpoint cooldown
    client._endpoint_cooldown_until["http://a.com"] = now + 30.0
    # b.com is in unsupported payload cooldown for "typeX"
    client._unsupported_payload_cooldown_until[("http://b.com", "typeX")] = now + 30.0
    
    candidates = client._candidate_base_urls("typeX")
    assert candidates == ["http://c.com"]
    
    # If all are in cooldown, it falls back to those NOT in unsupported_payload_cooldown
    client._endpoint_cooldown_until["http://c.com"] = now + 30.0
    candidates = client._candidate_base_urls("typeX")
    assert candidates == ["http://a.com", "http://c.com"]

@pytest.mark.asyncio
async def test_post_retries_different_endpoints():
    client = HyperliquidInfoClient(
        base_urls=["http://a.com", "http://b.com"],
    )
    client.rate_limit_delay = 0.0
    
    with patch.object(client, "_post_to_base_url", side_effect=[
        _EndpointUnavailableError("a down"),
        {"ok": True}
    ]) as mock_post_to_base:
        result = await client._post({"type": "something"})
        
    assert result == {"ok": True}
    assert mock_post_to_base.call_count == 2
    assert mock_post_to_base.call_args_list[0].args[0] == "http://a.com"
    assert mock_post_to_base.call_args_list[1].args[0] == "http://b.com"
    assert client._endpoint_cooldown_until["http://a.com"] > time.monotonic()

@pytest.mark.asyncio
async def test_post_raises_runtime_error_if_no_endpoints():
    client = HyperliquidInfoClient(base_urls=["http://a.com"])
    client.base_urls = []
    
    with pytest.raises(RuntimeError, match="No Hyperliquid info endpoints configured"):
        await client._post({"type": "something"})

@pytest.mark.asyncio
async def test_post_sets_unsupported_payload_cooldown():
    client = HyperliquidInfoClient(
        base_urls=["http://a.com", "http://b.com"],
        unsupported_payload_cooldown_seconds=300.0
    )
    client.rate_limit_delay = 0.0
    
    with patch.object(client, "_post_to_base_url", side_effect=[
        _EndpointPayloadUnsupportedError("a unsupported"),
        {"ok": True}
    ]) as mock_post_to_base:
        result = await client._post({"type": "typeX"})
        
    assert result == {"ok": True}
    assert client._unsupported_payload_cooldown_until[("http://a.com", "typeX")] > time.monotonic() + 200.0

@pytest.mark.asyncio
async def test_post_to_base_url_retries_on_generic_errors():
    client = HyperliquidInfoClient(base_urls=["http://a.com"])

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Error")
        mock_response.request_info = MagicMock()
        mock_response.history = ()
        mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=mock_response.request_info,
            history=mock_response.history,
            status=500,
            message="Internal Error",
        )

        # Configure mock_post to return a context manager that returns mock_response
        mock_post.return_value.__aenter__.return_value = mock_response

        with patch("asyncio.sleep", return_value=None) as mock_sleep:
            with pytest.raises(_EndpointUnavailableError):
                await client._post_to_base_url("http://a.com", {"type": "t"}, "t")

    # Should retry 3 times (0, 1, 2)
    assert mock_post.call_count == 3
    assert mock_sleep.call_count == 2 # Sleep after 1st and 2nd attempt
