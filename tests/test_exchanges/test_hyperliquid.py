"""Tests for Hyperliquid exchange adapter.

TDD RED Phase: These tests should FAIL until implementation is complete.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.exchanges.base import ExchangeHealth


class TestHyperliquidAdapter:
    """Tests for HyperliquidAdapter class."""

    def test_exchange_name(self):
        """T015: HyperliquidAdapter.exchange_name returns 'hyperliquid'."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()
        assert adapter.exchange_name == "hyperliquid"

    @pytest.mark.asyncio
    async def test_connect_creates_websocket(self):
        """T015: HyperliquidAdapter.connect() creates WebSocket connection."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()
        assert adapter._ws is None
        assert adapter._is_connected is False

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws

            await adapter.connect()

            assert adapter._is_connected is True
            mock_connect.assert_called_once()

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_closes_websocket(self):
        """HyperliquidAdapter.disconnect() closes WebSocket cleanly."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws

            await adapter.connect()
            assert adapter._is_connected is True

            await adapter.disconnect()

            assert adapter._is_connected is False
            mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_liquidations_is_explicitly_unsupported(self):
        """Legacy public-WS liquidation path should fail fast as unsupported."""
        from src.exchanges.hyperliquid import HyperliquidAdapter, UNSUPPORTED_REASON

        adapter = HyperliquidAdapter()

        with pytest.raises(NotImplementedError, match="unsupported"):
            async for _liq in adapter.stream_liquidations("BTCUSDT"):
                pass

        assert "node_fills_by_block" in UNSUPPORTED_REASON

    def test_normalize_symbol_removes_usdt(self):
        """T016: HyperliquidAdapter.normalize_symbol() converts to HL format."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()

        # Hyperliquid uses "BTC" not "BTCUSDT"
        # But normalize_symbol converts TO standard format
        # So "BTC" -> "BTCUSDT"
        assert adapter.normalize_symbol("BTC") == "BTCUSDT"
        assert adapter.normalize_symbol("ETH") == "ETHUSDT"

    def test_denormalize_symbol_for_subscription(self):
        """HyperliquidAdapter converts standard symbol to HL format for subscription."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()

        # For subscription we need to go the other way: BTCUSDT -> BTC
        assert adapter._denormalize_symbol("BTCUSDT") == "BTC"
        assert adapter._denormalize_symbol("ETHUSDT") == "ETH"

    @pytest.mark.asyncio
    async def test_health_check_when_connected(self):
        """HyperliquidAdapter.health_check() returns health when connected."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_connect.return_value = mock_ws

            await adapter.connect()
            health = await adapter.health_check()

            assert isinstance(health, ExchangeHealth)
            assert health.exchange == "hyperliquid"
            assert health.is_connected is True

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_health_check_when_disconnected(self):
        """HyperliquidAdapter.health_check() handles disconnected state."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()
        # Don't connect

        health = await adapter.health_check()

        assert isinstance(health, ExchangeHealth)
        assert health.exchange == "hyperliquid"
        assert health.is_connected is False

    @pytest.mark.asyncio
    async def test_fetch_historical_returns_empty(self):
        """HyperliquidAdapter.fetch_historical() returns empty (no historical API)."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()
        result = await adapter.fetch_historical(
            "BTCUSDT",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )

        assert result == []

    def test_side_mapping_a_is_short_liquidated(self):
        """Hyperliquid side A (Ask) means short position was liquidated."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()

        # A = Ask hit = forced buy = SHORT position liquidated
        assert adapter._normalize_side("A") == "short"

    def test_side_mapping_b_is_long_liquidated(self):
        """Hyperliquid side B (Bid) means long position was liquidated."""
        from src.exchanges.hyperliquid import HyperliquidAdapter

        adapter = HyperliquidAdapter()

        # B = Bid hit = forced sell = LONG position liquidated
        assert adapter._normalize_side("B") == "long"
