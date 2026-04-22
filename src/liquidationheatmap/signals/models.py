"""Pydantic models for Adaptive Signal Loop.

Signal and Feedback schemas for Redis pub/sub communication.
Uses Decimal for price precision per Constitution Section 1.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _utc_now() -> datetime:
    """Return current UTC time (Python 3.12+ compatible)."""
    return datetime.now(timezone.utc)


class LiquidationSignal(BaseModel):
    """Signal published to Redis when liquidation zone is detected.

    Published to channel: liquidation:signals:{symbol}

    Attributes:
        symbol: Trading pair (e.g., 'BTCUSDT')
        price: Liquidation price level (Decimal128 precision)
        side: Position side ('long' or 'short')
        confidence: Signal confidence from heatmap density (0.0-1.0)
        timestamp: When signal was generated
        source: Origin of signal (default: 'liquidationheatmap')
        signal_id: Unique identifier for tracking
    """

    symbol: str = Field(..., min_length=1, description="Trading pair symbol")
    price: Decimal = Field(..., gt=0, description="Liquidation price level")
    side: Literal["long", "short"] = Field(..., description="Position side")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Signal confidence (0.0-1.0)")
    timestamp: datetime = Field(default_factory=_utc_now, description="Signal timestamp")
    source: str = Field(default="liquidationheatmap", description="Signal source identifier")
    signal_id: str | None = Field(default=None, description="Unique signal identifier")

    @field_validator("price", mode="before")
    @classmethod
    def convert_price_to_decimal(cls, v):
        """Convert price to Decimal for precision."""
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v

    def to_redis_message(self) -> str:
        """Serialize to JSON for Redis pub/sub."""
        return self.model_dump_json()

    @classmethod
    def from_redis_message(cls, message: str) -> "LiquidationSignal":
        """Deserialize from Redis pub/sub message."""
        return cls.model_validate_json(message)

    model_config = {
        "json_encoders": {Decimal: str},
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "BTCUSDT",
                    "price": "95000.50",
                    "side": "long",
                    "confidence": 0.85,
                    "timestamp": "2025-12-28T10:30:00Z",
                    "source": "liquidationheatmap",
                }
            ]
        },
    }


class TradeFeedback(BaseModel):
    """P&L feedback received from trading systems (e.g., Nautilus).

    Received from channel: liquidation:feedback:{symbol}

    Attributes:
        symbol: Trading pair (e.g., 'BTCUSDT')
        signal_id: Reference to original signal
        entry_price: Trade entry price (Decimal128 precision)
        exit_price: Trade exit price (Decimal128 precision)
        pnl: Realized profit/loss (Decimal128 precision)
        timestamp: When feedback was recorded
        source: Origin of feedback ('nautilus' or 'manual')
    """

    symbol: str = Field(..., min_length=1, description="Trading pair symbol")
    signal_id: str = Field(..., min_length=1, description="Reference to original signal")
    entry_price: Decimal = Field(..., gt=0, description="Trade entry price")
    exit_price: Decimal = Field(..., gt=0, description="Trade exit price")
    pnl: Decimal = Field(..., description="Realized P&L (positive or negative)")
    timestamp: datetime = Field(default_factory=_utc_now, description="Feedback timestamp")
    source: Literal["nautilus", "manual"] = Field(..., description="Feedback source")

    @field_validator("entry_price", "exit_price", "pnl", mode="before")
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert numeric values to Decimal for precision."""
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v

    @property
    def is_profitable(self) -> bool:
        """Check if trade was profitable."""
        return self.pnl > 0

    @property
    def pnl_pct(self) -> float:
        """Calculate P&L as percentage of entry price."""
        return float(self.pnl / self.entry_price * 100)

    def to_redis_message(self) -> str:
        """Serialize to JSON for Redis pub/sub."""
        return self.model_dump_json()

    @classmethod
    def from_redis_message(cls, message: str) -> "TradeFeedback":
        """Deserialize from Redis pub/sub message."""
        return cls.model_validate_json(message)

    model_config = {
        "json_encoders": {Decimal: str},
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "BTCUSDT",
                    "signal_id": "abc123",
                    "entry_price": "95000.00",
                    "exit_price": "95500.00",
                    "pnl": "500.00",
                    "timestamp": "2025-12-28T11:00:00Z",
                    "source": "nautilus",
                }
            ]
        },
    }


class SignalMetrics(BaseModel):
    """Rolling metrics for signal performance.

    Returned by GET /signals/metrics endpoint.

    Attributes:
        symbol: Trading pair
        window: Metric window ('1h', '24h', '7d')
        hit_rate: Percentage of profitable signals
        total_signals: Total signals published in window
        feedback_count: Number of feedback records received
        avg_pnl: Average P&L per signal
    """

    symbol: str = Field(..., description="Trading pair symbol")
    window: Literal["1h", "24h", "7d"] = Field(..., description="Metric time window")
    hit_rate: float = Field(..., ge=0.0, le=1.0, description="Percentage of profitable signals")
    total_signals: int = Field(..., ge=0, description="Total signals in window")
    feedback_count: int = Field(..., ge=0, description="Feedback records received")
    avg_pnl: float = Field(..., description="Average P&L per signal")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "BTCUSDT",
                    "window": "24h",
                    "hit_rate": 0.75,
                    "total_signals": 96,
                    "feedback_count": 12,
                    "avg_pnl": 0.023,
                }
            ]
        }
    }


class SignalStatus(BaseModel):
    """Signal system status.

    Returned by GET /signals/status endpoint.

    Attributes:
        connected: Redis connection status
        last_publish: Timestamp of last signal published
        signals_published_24h: Count of signals in last 24 hours
        feedback_received_24h: Count of feedback in last 24 hours
    """

    connected: bool = Field(..., description="Redis connection status")
    last_publish: datetime | None = Field(None, description="Last signal timestamp")
    signals_published_24h: int = Field(..., ge=0, description="Signals in last 24h")
    feedback_received_24h: int = Field(..., ge=0, description="Feedback in last 24h")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "connected": True,
                    "last_publish": "2025-12-28T10:30:00Z",
                    "signals_published_24h": 96,
                    "feedback_received_24h": 12,
                }
            ]
        }
    }


class ContinuousReport(BaseModel):
    """Machine-readable report contract for continuous paper/testnet runs.

    Spec-040 requires these non-null lifecycle counters.
    """

    session_started_at: datetime = Field(..., description="Session start time for counter scoping")
    timestamp: datetime = Field(default_factory=_utc_now, description="Report generation time")
    runtime_seconds: float = Field(0.0, description="Total runtime in seconds")
    signals_seen: int = Field(0, description="Total signals observed by the runtime")
    signals_rejected: int = Field(0, description="Signals rejected by constraints")
    signals_accepted: int = Field(0, description="Signals accepted for execution")
    orders_submitted: int = Field(0, description="Orders sent to venue")
    orders_rejected: int = Field(0, description="Orders rejected by venue")
    orders_filled: int = Field(0, description="Orders successfully filled")
    positions_opened: int = Field(0, description="Positions successfully opened")
    positions_closed: int = Field(0, description="Positions successfully closed")
    feedback_published: int = Field(0, description="Feedback messages sent to Redis")
    feedback_persisted: int = Field(0, description="Feedback messages saved to DuckDB")
    persistence_consistent: bool = Field(
        True,
        description="Whether feedback_published matches feedback_persisted for the session",
    )
    report_status: Literal["ok", "blocked"] = Field(
        "ok",
        description="Whether the report is acceptable for green evidence gating",
    )
    blocking_issues: list[str] = Field(
        default_factory=list,
        description="Blocking issues which prevent a green evidence result",
    )
    residual_open_positions: int = Field(0, description="Open positions remaining at shutdown")
    residual_open_orders: int = Field(0, description="Open orders remaining at shutdown")
