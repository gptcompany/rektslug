"""Models for vendored liquidation streams."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Side(Enum):
    LONG = "long"
    SHORT = "short"


class Venue(Enum):
    BINANCE = "binance"
    BYBIT = "bybit"
    HYPERLIQUID = "hyperliquid"


class Liquidation(BaseModel):
    """Pydantic contract for real-time WebSocket liquidation events."""

    timestamp: datetime = Field(..., description="Timestamp of the liquidation event")
    symbol: str = Field(..., description="Symbol being liquidated (e.g. BTCUSDT-PERP)")
    venue: Venue = Field(..., description="Exchange where the liquidation occurred")
    side: Side = Field(..., description="Side of the position that was liquidated")
    price: float = Field(..., description="Price at which the liquidation order was filled", gt=0)
    quantity: float = Field(..., description="Quantity of the liquidated position", gt=0)
    value: float = Field(
        ..., description="Notional value of the liquidation (price * quantity)", ge=0
    )
