"""Native WebSocket streams for liquidation events.

Bypasses CCXT to use exchange-native WebSocket APIs for real-time liquidation data.
"""

import asyncio
import contextlib
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from src.liquidationheatmap.streams.models import Liquidation, Side, Venue

logger = logging.getLogger(__name__)
UTC = timezone.utc
HYPERLIQUID_UNSUPPORTED_REASON = (
    "Public Hyperliquid liquidation streaming is unsupported: the public trades feed "
    "does not provide a stable realized-liquidation signal for this runtime."
)


class BaseLiquidationStream(ABC):
    """Base class for native liquidation WebSocket streams."""

    def __init__(
        self,
        symbols: list[str],
        callback: Callable[[Liquidation], None],
        status_callback: Callable[[Venue, str, dict[str, Any]], None] | None = None,
    ):
        self.symbols = symbols
        self.callback = callback
        self.status_callback = status_callback
        self._running = False
        self._ws: Any = None
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    def _emit_status(self, event: str, **details: Any) -> None:
        """Emit runtime status updates to the daemon."""
        if self.status_callback:
            self.status_callback(self.venue, event, details)

    @property
    @abstractmethod
    def venue(self) -> Venue:
        """Return the venue for this stream."""
        pass

    @property
    @abstractmethod
    def ws_url(self) -> str:
        """Return the WebSocket URL."""
        pass

    @abstractmethod
    def parse_message(self, data: dict) -> Liquidation | None:
        """Parse a WebSocket message into a Liquidation object."""
        pass

    async def start(self) -> None:
        """Start the WebSocket stream with auto-reconnect."""
        self._running = True
        self._emit_status("starting", reconnect_delay=self._reconnect_delay)
        logger.info(f"Starting {self.venue.value} liquidation stream for {self.symbols}")

        while self._running:
            try:
                await self._connect_and_stream()
            except ConnectionClosed as e:
                if not self._running:
                    break
                self._emit_status(
                    "error",
                    error=str(e),
                    reconnect_delay=self._reconnect_delay,
                )
                logger.warning(
                    f"{self.venue.value} WebSocket closed: {e}. "
                    f"Reconnecting in {self._reconnect_delay}s..."
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
            except Exception as e:
                if not self._running:
                    break
                self._emit_status(
                    "error",
                    error=str(e),
                    reconnect_delay=self._reconnect_delay,
                )
                logger.error(
                    f"{self.venue.value} stream error: {e}. "
                    f"Reconnecting in {self._reconnect_delay}s..."
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def _connect_and_stream(self) -> None:
        """Connect to WebSocket and process messages."""
        async with websockets.connect(self.ws_url, ping_interval=20) as ws:
            self._ws = ws
            self._reconnect_delay = 1.0  # Reset on successful connect
            self._emit_status("connected")
            logger.info(f"Connected to {self.venue.value} liquidation stream")

            # Send subscription if needed
            await self._subscribe(ws)

            async for message in ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    liquidation = self.parse_message(data)
                    if liquidation:
                        self.callback(liquidation)
                        self._emit_status("event", symbol=liquidation.symbol)
                except json.JSONDecodeError:
                    msg_preview = message.decode() if isinstance(message, bytes) else message
                    logger.warning(f"Invalid JSON from {self.venue.value}: {msg_preview[:100]}")
                except Exception as e:
                    logger.error(f"Error parsing {self.venue.value} message: {e}")

    async def _subscribe(self, ws) -> None:
        """Send subscription message if required by the exchange."""
        pass  # Override in subclasses if needed

    async def stop(self) -> None:
        """Stop the WebSocket stream."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._emit_status("stopped")
        logger.info(f"Stopped {self.venue.value} liquidation stream")


class BinanceLiquidationStream(BaseLiquidationStream):
    """Binance Futures liquidation stream.

    Uses the aggregate forceOrder stream for all symbols.
    Endpoint: wss://fstream.binance.com/ws/!forceOrder@arr
    """

    @property
    def venue(self) -> Venue:
        return Venue.BINANCE

    @property
    def ws_url(self) -> str:
        return "wss://fstream.binance.com/ws/!forceOrder@arr"

    def parse_message(self, data: dict) -> Liquidation | None:
        """Parse Binance forceOrder message."""
        if data.get("e") != "forceOrder":
            return None

        order = data.get("o", {})
        symbol = order.get("s", "")

        # Build allowed raw symbols from config (e.g. BTCUSDT-PERP → BTCUSDT)
        allowed_raw = {
            s.upper().replace("-PERP", "").replace("/", "").replace(":USDT", "")
            for s in self.symbols
        }
        # Ensure USDT suffix for matching
        allowed_raw = {s if s.endswith("USDT") else s + "USDT" for s in allowed_raw}

        if symbol not in allowed_raw:
            return None

        try:
            price = float(order.get("ap", order.get("p", 0)))
            quantity = float(order.get("q", 0))
            if price <= 0 or quantity <= 0:
                return None
            return Liquidation(
                timestamp=datetime.fromtimestamp(order.get("T", data.get("E", 0)) / 1000, tz=UTC),
                symbol=f"{symbol}-PERP" if not symbol.endswith("-PERP") else symbol,
                venue=Venue.BINANCE,
                side=Side.LONG if order.get("S") == "SELL" else Side.SHORT,
                price=price,
                quantity=quantity,
                value=price * quantity,
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Binance liquidation: {e}")
            return None


class HyperliquidLiquidationStream(BaseLiquidationStream):
    """Legacy Hyperliquid liquidation stream placeholder.

    Public Hyperliquid liquidation streaming is not supported in the active
    runtime. This class is retained only for backwards compatibility in tests
    and older imports.
    """

    @property
    def venue(self) -> Venue:
        return Venue.HYPERLIQUID

    @property
    def ws_url(self) -> str:
        return "wss://api.hyperliquid.xyz/ws"

    async def _subscribe(self, ws) -> None:
        """Subscribe to trades for each symbol (liquidations appear as trades)."""
        for s in self.symbols:
            coin = s.upper().replace("-PERP", "").replace("USDT", "").replace("/", "")
            subscribe_msg = {
                "method": "subscribe",
                "subscription": {"type": "trades", "coin": coin},
            }
            await ws.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to Hyperliquid trades for {coin}")

    def parse_message(self, data: dict) -> Liquidation | None:
        """Parse Hyperliquid trade message for liquidations."""
        if data.get("channel") != "trades":
            return None

        trades = data.get("data", [])
        for trade in trades:
            if not trade.get("liquidation"):
                continue

            coin = trade.get("coin", "")

            try:
                price = float(trade.get("px", 0))
                quantity = float(trade.get("sz", 0))
                if price <= 0 or quantity <= 0:
                    continue
                return Liquidation(
                    timestamp=datetime.fromtimestamp(trade.get("time", 0) / 1000, tz=UTC),
                    symbol=f"{coin}USDT-PERP",
                    venue=Venue.HYPERLIQUID,
                    side=Side.LONG if trade.get("side") == "A" else Side.SHORT,
                    price=price,
                    quantity=quantity,
                    value=price * quantity,
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse Hyperliquid liquidation: {e}")

        return None


class LiquidationStreamManager:
    """Manages multiple liquidation streams across exchanges."""

    def __init__(
        self,
        symbols: list[str],
        callback: Callable[[Liquidation], None],
        exchanges: list[str] | None = None,
        status_callback: Callable[[Venue, str, dict[str, Any]], None] | None = None,
    ):
        self.symbols = symbols
        self.callback = callback
        self.exchanges = exchanges or ["binance", "hyperliquid"]
        self.status_callback = status_callback
        self._streams: list[BaseLiquidationStream] = []
        self._tasks: list[asyncio.Task] = []

    def _create_streams(self) -> list[BaseLiquidationStream]:
        """Create stream instances for configured exchanges."""
        streams: list[BaseLiquidationStream] = []
        for exchange in self.exchanges:
            if exchange.lower() == "binance":
                streams.append(
                    BinanceLiquidationStream(
                        self.symbols,
                        self.callback,
                        status_callback=getattr(self, "status_callback", None),
                    )
                )
            elif exchange.lower() == "hyperliquid":
                if self.status_callback:
                    self.status_callback(
                        Venue.HYPERLIQUID,
                        "unsupported",
                        {"reason": HYPERLIQUID_UNSUPPORTED_REASON},
                    )
                logger.warning(
                    "Skipping Hyperliquid liquidation stream: %s",
                    HYPERLIQUID_UNSUPPORTED_REASON,
                )
        return streams

    async def start(self) -> None:
        """Start all liquidation streams."""
        self._streams = self._create_streams()
        self._tasks = [asyncio.create_task(stream.start()) for stream in self._streams]
        logger.info(f"Started {len(self._streams)} liquidation streams for {self.symbols}")

    async def stop(self) -> None:
        """Stop all liquidation streams."""
        for stream in self._streams:
            await stream.stop()

        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self._streams.clear()
        self._tasks.clear()
        logger.info("All liquidation streams stopped")
