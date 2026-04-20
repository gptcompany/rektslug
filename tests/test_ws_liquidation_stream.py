"""Tests for vendored WebSocket liquidation stream classes."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.liquidationheatmap.streams.liquidations import (
    HyperliquidLiquidationStream,
    BinanceLiquidationStream,
)


class TestHyperliquidLiquidationStream:
    def test_parse_liquidation_trade(self):
        """WS event with liquidation=true should produce a Liquidation."""
        received = []
        stream = HyperliquidLiquidationStream(
            symbols=["BTCUSDT-PERP"],
            callback=received.append,
        )
        msg = {
            "channel": "trades",
            "data": [
                {
                    "coin": "BTC",
                    "side": "A",
                    "px": "72100.0",
                    "sz": "0.5",
                    "time": 1713600000000,
                    "liquidation": True,
                }
            ],
        }
        result = stream.parse_message(msg)
        assert result is not None
        assert result.symbol == "BTCUSDT-PERP"
        assert result.price == 72100.0
        assert result.side.value == "long"

    def test_ignore_non_liquidation_trade(self):
        stream = HyperliquidLiquidationStream(
            symbols=["BTCUSDT-PERP"],
            callback=lambda x: None,
        )
        msg = {
            "channel": "trades",
            "data": [{"coin": "BTC", "side": "A", "px": "72000", "sz": "1", "time": 1}],
        }
        result = stream.parse_message(msg)
        assert result is None


class TestBinanceLiquidationStream:
    def test_parse_force_order(self):
        received = []
        stream = BinanceLiquidationStream(
            symbols=["BTCUSDT-PERP"],
            callback=received.append,
        )
        msg = {
            "e": "forceOrder",
            "E": 1713600000000,
            "o": {
                "s": "BTCUSDT",
                "S": "SELL",
                "o": "LIMIT",
                "f": "IOC",
                "q": "0.014",
                "p": "72000",
                "ap": "72050",
                "X": "FILLED",
                "l": "0.014",
                "z": "0.014",
                "T": 1713600000000,
            },
        }
        result = stream.parse_message(msg)
        assert result is not None
        assert result.price == 72050.0
        assert result.side.value == "long"