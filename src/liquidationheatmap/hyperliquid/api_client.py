"""Hyperliquid Info API client."""

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import aiohttp

from src.liquidationheatmap.hyperliquid.models import (
    AccountAbstraction,
    AssetMetaSnapshot,
    BorrowLendReserveState,
    BorrowLendUserState,
    ClearinghouseUserState,
    SpotClearinghouseState,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class _EndpointUnavailableError(RuntimeError):
    """Raised when an endpoint is temporarily unavailable."""


class _EndpointPayloadUnsupportedError(RuntimeError):
    """Raised when an endpoint does not support a specific payload type."""


class HyperliquidInfoClient:
    """Async client for Hyperliquid Info API."""

    DEFAULT_BASE_URL = "https://api.hyperliquid.xyz/info"
    DEFAULT_REQUEST_TIMEOUT_SECONDS = 5.0
    DEFAULT_ENDPOINT_COOLDOWN_SECONDS = 60.0
    DEFAULT_UNSUPPORTED_PAYLOAD_COOLDOWN_SECONDS = 300.0

    def __init__(
        self,
        requests_per_minute: int = 10,
        *,
        base_url: str | None = None,
        base_urls: list[str] | tuple[str, ...] | None = None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        endpoint_cooldown_seconds: float = DEFAULT_ENDPOINT_COOLDOWN_SECONDS,
        unsupported_payload_cooldown_seconds: float = DEFAULT_UNSUPPORTED_PAYLOAD_COOLDOWN_SECONDS,
    ):
        self.rate_limit_delay = 60.0 / requests_per_minute
        self._semaphore = asyncio.Semaphore(5)
        self.request_timeout_seconds = request_timeout_seconds
        self.endpoint_cooldown_seconds = endpoint_cooldown_seconds
        self.unsupported_payload_cooldown_seconds = unsupported_payload_cooldown_seconds
        self.base_urls = self._resolve_base_urls(
            base_url=base_url,
            base_urls=base_urls,
        )
        self.base_url = self.base_urls[0]
        self._endpoint_cooldown_until: dict[str, float] = {}
        self._unsupported_payload_cooldown_until: dict[tuple[str, str], float] = {}

    @classmethod
    def _resolve_base_urls(
        cls,
        *,
        base_url: str | None,
        base_urls: list[str] | tuple[str, ...] | None,
    ) -> list[str]:
        if base_urls:
            return cls._normalize_base_urls(base_urls)
        if base_url:
            return cls._normalize_base_urls([base_url])

        env_fallback_urls = (
            os.getenv("HEATMAP_HYPERLIQUID_INFO_FALLBACK_URLS")
            or os.getenv("HYPERLIQUID_INFO_FALLBACK_URLS")
        )
        if env_fallback_urls:
            return cls._normalize_base_urls(env_fallback_urls.split(","))

        env_base_url = (
            os.getenv("HEATMAP_HYPERLIQUID_INFO_URL")
            or os.getenv("HYPERLIQUID_INFO_URL")
            or cls.DEFAULT_BASE_URL
        )
        return cls._normalize_base_urls([env_base_url])

    @staticmethod
    def _normalize_base_urls(base_urls: list[str] | tuple[str, ...]) -> list[str]:
        normalized: list[str] = []
        for base_url in base_urls:
            url = str(base_url).strip()
            if not url or url in normalized:
                continue
            normalized.append(url)
        if not normalized:
            raise ValueError("At least one Hyperliquid info endpoint is required")
        return normalized

    @staticmethod
    def _payload_type(payload: dict[str, Any]) -> str:
        return str(payload.get("type", "unknown"))

    @staticmethod
    def _looks_like_payload_unsupported(raw_body: str) -> bool:
        body = raw_body.strip()
        if not body:
            return False
        return (
            "Failed to deserialize" in body
            or "unknown variant" in body.lower()
            or "unknown field" in body.lower()
        )

    def _candidate_base_urls(self, payload_type: str) -> list[str]:
        now = time.monotonic()
        candidates = [
            base_url
            for base_url in self.base_urls
            if self._unsupported_payload_cooldown_until.get((base_url, payload_type), 0.0) <= now
            and self._endpoint_cooldown_until.get(base_url, 0.0) <= now
        ]
        if candidates:
            return candidates
        return [
            base_url
            for base_url in self.base_urls
            if self._unsupported_payload_cooldown_until.get((base_url, payload_type), 0.0) <= now
        ]

    async def _post_to_base_url(
        self,
        base_url: str,
        payload: dict[str, Any],
        payload_type: str,
    ) -> Any:
        backoff = 1.0
        max_retries = 3
        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(max_retries):
                try:
                    async with session.post(
                        base_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    ) as response:
                        raw_body = await response.text()
                        if response.status == 429:
                            raise aiohttp.ClientResponseError(
                                response.request_info,
                                response.history,
                                status=response.status,
                                message="Rate limit exceeded",
                            )
                        if response.status >= 400:
                            if self._looks_like_payload_unsupported(raw_body):
                                raise _EndpointPayloadUnsupportedError(
                                    f"{base_url} does not support payload {payload_type}"
                                )
                            response.raise_for_status()
                        try:
                            return json.loads(raw_body)
                        except json.JSONDecodeError as exc:
                            if self._looks_like_payload_unsupported(raw_body):
                                raise _EndpointPayloadUnsupportedError(
                                    f"{base_url} does not support payload {payload_type}"
                                ) from exc
                            raise _EndpointUnavailableError(
                                f"{base_url} returned non-JSON response for payload {payload_type}"
                            ) from exc
                except _EndpointPayloadUnsupportedError:
                    raise
                except (
                    aiohttp.ClientResponseError,
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    _EndpointUnavailableError,
                ) as exc:
                    if attempt == max_retries - 1:
                        raise _EndpointUnavailableError(
                            f"Hyperliquid endpoint {base_url} failed for payload {payload_type}"
                        ) from exc
                    await asyncio.sleep(backoff)
                    backoff *= 2.0

    async def _post(self, payload: dict[str, Any]) -> Any:
        """Make a POST request with retry logic and rate limiting."""
        payload_type = self._payload_type(payload)
        async with self._semaphore:
            last_error: Exception | None = None
            for base_url in self._candidate_base_urls(payload_type):
                try:
                    await asyncio.sleep(self.rate_limit_delay)
                    return await self._post_to_base_url(
                        base_url,
                        payload,
                        payload_type,
                    )
                except _EndpointPayloadUnsupportedError as exc:
                    self._unsupported_payload_cooldown_until[(base_url, payload_type)] = (
                        time.monotonic() + self.unsupported_payload_cooldown_seconds
                    )
                    last_error = exc
                    logger.warning("%s", exc)
                except _EndpointUnavailableError as exc:
                    self._endpoint_cooldown_until[base_url] = (
                        time.monotonic() + self.endpoint_cooldown_seconds
                    )
                    last_error = exc
                    logger.warning("%s", exc)

            if last_error is not None:
                raise last_error
            raise RuntimeError("No Hyperliquid info endpoints configured")

    async def get_clearinghouse_state(self, user: str) -> ClearinghouseUserState:
        """Get clearinghouse state for a user."""
        payload = await self._post({"type": "clearinghouseState", "user": user})
        return ClearinghouseUserState.from_api(payload)

    async def get_spot_clearinghouse_state(self, user: str) -> SpotClearinghouseState:
        """Get spot clearinghouse state for a user."""
        payload = await self._post({"type": "spotClearinghouseState", "user": user})
        return SpotClearinghouseState.from_api(payload)

    async def get_user_abstraction(self, user: str) -> AccountAbstraction:
        """Get account abstraction mode for a user."""
        payload = await self._post({"type": "userAbstraction", "user": user})
        return AccountAbstraction.from_api(payload)

    async def get_borrow_lend_user_state(self, user: str) -> BorrowLendUserState:
        """Get borrow/lend user state for a user."""
        payload = await self._post({"type": "borrowLendUserState", "user": user})
        return BorrowLendUserState.from_api(payload)

    async def get_all_borrow_lend_reserve_states(
        self,
    ) -> dict[int, BorrowLendReserveState]:
        """Get all borrow/lend reserve states keyed by token id."""
        payload = await self._post({"type": "allBorrowLendReserveStates"})
        reserve_states: dict[int, BorrowLendReserveState] = {}
        for item in payload:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            reserve_states[int(item[0])] = BorrowLendReserveState.from_api(item[1])
        return reserve_states

    async def get_asset_meta(self) -> AssetMetaSnapshot:
        """Get asset metadata and context."""
        payload = await self._post({"type": "metaAndAssetCtxs"})
        return AssetMetaSnapshot.from_api(payload)

    async def _fetch_batch(
        self,
        users: list[str],
        fetcher: Callable[[str], Awaitable[T]],
        *,
        label: str,
    ) -> dict[str, T]:
        """Fetch a per-user resource concurrently and keep partial successes."""
        results: dict[str, T] = {}

        async def fetch_user(user: str) -> None:
            try:
                results[user] = await fetcher(user)
            except Exception as exc:
                logger.error("Failed to fetch %s for %s: %s", label, user, exc)

        await asyncio.gather(*(fetch_user(user) for user in users))
        return results

    async def get_clearinghouse_states_batch(
        self, users: list[str]
    ) -> dict[str, ClearinghouseUserState]:
        """Get clearinghouse state for multiple users concurrently."""
        return await self._fetch_batch(
            users,
            self.get_clearinghouse_state,
            label="clearinghouse state",
        )

    async def get_spot_clearinghouse_states_batch(
        self, users: list[str]
    ) -> dict[str, SpotClearinghouseState]:
        """Get spot clearinghouse state for multiple users concurrently."""
        return await self._fetch_batch(
            users,
            self.get_spot_clearinghouse_state,
            label="spot clearinghouse state",
        )

    async def get_user_abstractions_batch(
        self, users: list[str]
    ) -> dict[str, AccountAbstraction]:
        """Get account abstraction state for multiple users concurrently."""
        return await self._fetch_batch(
            users,
            self.get_user_abstraction,
            label="user abstraction",
        )

    async def get_borrow_lend_user_states_batch(
        self, users: list[str]
    ) -> dict[str, BorrowLendUserState]:
        """Get borrow/lend state for multiple users concurrently."""
        return await self._fetch_batch(
            users,
            self.get_borrow_lend_user_state,
            label="borrow/lend user state",
        )
