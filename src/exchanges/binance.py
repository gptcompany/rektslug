"""Binance Futures adapter using REST API polling.

Uses REST /fapi/v1/forceOrders instead of WebSocket due to 403 errors.
Polls every 5 seconds with deduplication.
"""

import asyncio
import logging
import hmac
import hashlib
import urllib.parse
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import aiohttp

from src.exchanges.base import ExchangeAdapter, ExchangeHealth, NormalizedLiquidation
from src.liquidationheatmap.utils.secrets import get_secret

logger = logging.getLogger(__name__)


class BinanceAdapter(ExchangeAdapter):
    """Binance Futures adapter (REST only - WebSocket has auth issues)."""

    BASE_URL = "https://fapi.binance.com"
    POLL_INTERVAL = 5  # seconds
    DEDUP_WINDOW = 600  # 10 minutes

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._is_connected = False
        self._last_heartbeat: Optional[datetime] = None
        self._message_count = 0
        self._error_count = 0
        self._seen_order_ids: set[int] = set()
        self._seen_order_timestamps: dict[int, float] = {}
        self.api_key = get_secret("BINANCE_API_KEY")
        self.api_secret = get_secret("BINANCE_API_SECRET")

    @property
    def exchange_name(self) -> str:
        return "binance"

    async def connect(self) -> None:
        """Initialize HTTP session."""
        if not self._session:
            self._session = aiohttp.ClientSession()
            self._is_connected = True
            self._last_heartbeat = datetime.now(timezone.utc)
            logger.info("Binance adapter connected (REST)")

    async def disconnect(self) -> None:
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
            self._is_connected = False
            logger.info("Binance adapter disconnected")

    async def stream_liquidations(
        self, symbol: str = "BTCUSDT"
    ) -> AsyncIterator[NormalizedLiquidation]:
        """Stream liquidations via REST polling (WebSocket blocked).

        NOTE: This is a workaround for WebSocket 403 errors.
        Polls /fapi/v1/forceOrders every 5 seconds.
        """
        if not self._is_connected:
            await self.connect()

        while self._is_connected:
            try:
                # Clean up old dedup entries
                self._cleanup_dedup_cache()

                async with self._session.get(
                    f"{self.BASE_URL}/fapi/v1/forceOrders",
                    params={"symbol": symbol, "limit": 100},
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

                    for order in data:
                        order_id = order["orderId"]
                        if order_id in self._seen_order_ids:
                            continue

                        self._seen_order_ids.add(order_id)
                        self._seen_order_timestamps[order_id] = asyncio.get_event_loop().time()
                        self._message_count += 1
                        self._last_heartbeat = datetime.now(timezone.utc)

                        yield NormalizedLiquidation(
                            exchange="binance",
                            symbol=self.normalize_symbol(order["symbol"]),
                            price=float(order["price"]),
                            quantity=float(order["origQty"]),
                            value_usd=float(order["price"]) * float(order["origQty"]),
                            side=self._normalize_side(order["side"]),
                            timestamp=datetime.fromtimestamp(order["time"] / 1000, tz=timezone.utc),
                            raw_data=order,
                            liquidation_type="forced",
                            is_validated=True,
                            confidence=1.0,
                        )

                await asyncio.sleep(self.POLL_INTERVAL)

            except Exception as e:
                self._error_count += 1
                logger.error(f"Binance polling error: {e}")
                await asyncio.sleep(self.POLL_INTERVAL * 2)  # Back off on error

    def _cleanup_dedup_cache(self) -> None:
        """Remove order IDs older than DEDUP_WINDOW."""
        current_time = asyncio.get_event_loop().time()
        expired = [
            order_id
            for order_id, ts in self._seen_order_timestamps.items()
            if current_time - ts > self.DEDUP_WINDOW
        ]
        for order_id in expired:
            self._seen_order_ids.discard(order_id)
            del self._seen_order_timestamps[order_id]

    def _normalize_side(self, side: str) -> str:
        """Convert Binance side to standard format.

        Binance liquidation:
        - BUY = market buy to close short = SHORT position liquidated
        - SELL = market sell to close long = LONG position liquidated
        """
        if side == "SELL":
            return "long"
        elif side == "BUY":
            return "short"
        return side.lower()

    async def fetch_historical(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> list[NormalizedLiquidation]:
        """Fetch from DuckDB (already ingested via scripts).

        Returns empty list - historical data handled by db_service.
        """
        return []

    async def health_check(self) -> ExchangeHealth:
        """Ping Binance API."""
        if not self._session or not self._is_connected:
            return ExchangeHealth(
                exchange="binance",
                is_connected=False,
                last_heartbeat=self._last_heartbeat or datetime.now(timezone.utc),
                message_count=self._message_count,
                error_count=self._error_count,
                uptime_percent=0.0,
            )

        try:
            async with self._session.get(f"{self.BASE_URL}/fapi/v1/ping") as resp:
                resp.raise_for_status()
                return ExchangeHealth(
                    exchange="binance",
                    is_connected=True,
                    last_heartbeat=datetime.now(timezone.utc),
                    message_count=self._message_count,
                    error_count=self._error_count,
                    uptime_percent=99.5,  # Binance is highly reliable
                )
        except Exception as e:
            logger.error(f"Binance health check failed: {e}")
            return ExchangeHealth(
                exchange="binance",
                is_connected=False,
                last_heartbeat=self._last_heartbeat or datetime.now(timezone.utc),
                message_count=self._message_count,
                error_count=self._error_count + 1,
                uptime_percent=0.0,
            )

    def normalize_symbol(self, exchange_symbol: str) -> str:
        """Binance already uses standard format."""
        return exchange_symbol

    async def fetch_account_info(self) -> dict:
        """Fetch account information from Binance Futures API."""
        if not self._is_connected:
            await self.connect()

        if not self.api_key or not self.api_secret:
            logger.error("Binance API key or secret not configured.")
            return {}

        endpoint = f"{self.BASE_URL}/fapi/v2/account"
        timestamp = int(time.time() * 1000)
        params = {"timestamp": timestamp}
        query_string = urllib.parse.urlencode(params)

        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        params["signature"] = signature

        try:
            async with self._session.get(
                endpoint, headers={"X-MBX-APIKEY": self.api_key}, params=params
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data
        except Exception as e:
            logger.error(f"Failed to fetch Binance account info: {e}")
            return {}
