"""Tests for vendored WebSocket liquidation stream classes."""
from unittest.mock import MagicMock

import pytest

from src.liquidationheatmap.streams.liquidations import (
    BinanceLiquidationStream,
    HYPERLIQUID_UNSUPPORTED_REASON,
    LiquidationStreamManager,
)
from src.liquidationheatmap.streams.models import Venue


class TestLiquidationStreamManager:
    def test_skips_hyperliquid_as_unsupported(self):
        status_callback = MagicMock()
        manager = LiquidationStreamManager(
            symbols=["BTCUSDT-PERP"],
            callback=lambda x: None,
            exchanges=["binance", "hyperliquid"],
            status_callback=status_callback,
        )

        streams = manager._create_streams()

        assert len(streams) == 1
        status_callback.assert_called_once_with(
            Venue.HYPERLIQUID,
            "unsupported",
            {"reason": HYPERLIQUID_UNSUPPORTED_REASON},
        )


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
