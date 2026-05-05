"""Legacy Hyperliquid liquidation adapter.

The active runtime does not use the public Hyperliquid WebSocket as a source of
realized liquidation events. Historical and validated Hyperliquid liquidation
data comes from `node_fills_by_block`, while the public Hyperliquid liq-map uses
the sidecar/cache path.
"""

import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Optional, cast

import websockets

from src.exchanges.base import ExchangeAdapter, ExchangeHealth, NormalizedLiquidation

logger = logging.getLogger(__name__)
UNSUPPORTED_REASON = (
    "Public Hyperliquid liquidation streaming is unsupported in rektslug; "
    "use node_fills_by_block for realized liquidations or /liquidations/hl-public-map "
    "for the sidecar surface."
)


class HyperliquidAdapter(ExchangeAdapter):
    """Hyperliquid DEX adapter (WebSocket only)."""

    WS_URL = "wss://api.hyperliquid.xyz/ws"

    def __init__(self):
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._is_connected = False
        self._last_heartbeat: Optional[datetime] = None
        self._message_count = 0
        self._error_count = 0

    @property
    def exchange_name(self) -> str:
        return "hyperliquid"

    async def connect(self) -> None:
        """Connect to Hyperliquid WebSocket."""
        try:
            self._ws = await websockets.connect(self.WS_URL)
            self._is_connected = True
            self._last_heartbeat = datetime.now(timezone.utc)
            logger.info("Hyperliquid adapter connected (WebSocket)")
        except Exception as e:
            logger.error(f"Hyperliquid connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        """Close WebSocket."""
        if self._ws:
            await self._ws.close()
            self._ws = None
            self._is_connected = False
            logger.info("Hyperliquid adapter disconnected")

    async def stream_liquidations(
        self, symbol: str = "BTCUSDT"
    ) -> AsyncIterator[NormalizedLiquidation]:
        """Raise explicitly because this legacy public-WS path is unsupported."""
        if False:  # pragma: no cover - keeps this method an async iterator
            yield cast(NormalizedLiquidation, None)
        raise NotImplementedError(UNSUPPORTED_REASON)

    def _normalize_side(self, side: str) -> str:
        """Convert Hyperliquid side to standard format.

        Hyperliquid uses:
        - A (Ask) = trade hit ask = forced buy = SHORT position liquidated
        - B (Bid) = trade hit bid = forced sell = LONG position liquidated
        """
        if side == "A":
            return "short"
        elif side == "B":
            return "long"
        return side.lower()

    def _denormalize_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Hyperliquid format for subscription.

        "BTCUSDT" -> "BTC"
        """
        if symbol.endswith("USDT"):
            return symbol[:-4]
        return symbol

    async def fetch_historical(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> list[NormalizedLiquidation]:
        """Hyperliquid doesn't provide historical liquidation API."""
        return []

    async def health_check(self) -> ExchangeHealth:
        """Check WebSocket connection."""
        is_alive = self._ws is not None and not self._ws.closed if self._ws else False

        return ExchangeHealth(
            exchange="hyperliquid",
            is_connected=is_alive and self._is_connected,
            last_heartbeat=self._last_heartbeat or datetime.now(timezone.utc),
            message_count=self._message_count,
            error_count=self._error_count,
            uptime_percent=95.0 if is_alive else 0.0,
        )

    def normalize_symbol(self, exchange_symbol: str) -> str:
        """Convert Hyperliquid symbol to standard format.

        "BTC" -> "BTCUSDT"
        """
        if not exchange_symbol.endswith("USDT"):
            return f"{exchange_symbol}USDT"
        return exchange_symbol
