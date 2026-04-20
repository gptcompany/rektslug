"""Minimal models for vendored liquidation streams."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Side(Enum):
    LONG = "long"
    SHORT = "short"


class Venue(Enum):
    BINANCE = "binance"
    BYBIT = "bybit"
    HYPERLIQUID = "hyperliquid"


@dataclass
class Liquidation:
    timestamp: datetime
    symbol: str
    venue: Venue
    side: Side
    price: float
    quantity: float
    value: float
