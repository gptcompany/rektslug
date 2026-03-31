"""Hyperliquid Info API client."""

import asyncio
import logging
from typing import Any

import aiohttp

from src.liquidationheatmap.hyperliquid.models import (
    AssetMetaSnapshot,
    ClearinghouseUserState,
)

logger = logging.getLogger(__name__)


class HyperliquidInfoClient:
    """Async client for Hyperliquid Info API."""

    BASE_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self, requests_per_minute: int = 10):
        self.rate_limit_delay = 60.0 / requests_per_minute
        self._semaphore = asyncio.Semaphore(5)

    async def _post(self, payload: dict[str, Any]) -> Any:
        """Make a POST request with retry logic and rate limiting."""
        async with self._semaphore:
            # Simple rate limiting wait
            await asyncio.sleep(self.rate_limit_delay)
            
            backoff = 1.0
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            self.BASE_URL,
                            json=payload,
                            headers={"Content-Type": "application/json"}
                        ) as response:
                            if response.status == 429:
                                raise aiohttp.ClientResponseError(
                                    response.request_info,
                                    response.history,
                                    status=response.status,
                                    message="Rate limit exceeded"
                                )
                            response.raise_for_status()
                            return await response.json()
                except (aiohttp.ClientResponseError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Hyperliquid API request failed after {max_retries} attempts: {e}")
                        raise
                    
                    # If rate limited or transient error, wait and retry
                    await asyncio.sleep(backoff)
                    backoff *= 2.0

    async def get_clearinghouse_state(self, user: str) -> ClearinghouseUserState:
        """Get clearinghouse state for a user."""
        payload = await self._post({"type": "clearinghouseState", "user": user})
        return ClearinghouseUserState.from_api(payload)

    async def get_asset_meta(self) -> AssetMetaSnapshot:
        """Get asset metadata and context."""
        payload = await self._post({"type": "metaAndAssetCtxs"})
        return AssetMetaSnapshot.from_api(payload)

    async def get_clearinghouse_states_batch(
        self, users: list[str]
    ) -> dict[str, ClearinghouseUserState]:
        """Get clearinghouse state for multiple users concurrently."""
        results: dict[str, ClearinghouseUserState] = {}
        
        async def fetch_user(user: str):
            try:
                state = await self.get_clearinghouse_state(user)
                results[user] = state
            except Exception as e:
                logger.error(f"Failed to fetch clearinghouse state for {user}: {e}")
                
        # Gather all requests
        await asyncio.gather(*(fetch_user(u) for u in users))
        
        return results
