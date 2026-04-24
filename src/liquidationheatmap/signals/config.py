"""Configuration for Adaptive Signal Loop.

Redis connection settings and signal parameters loaded from environment variables.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


def _default_redis_host() -> str:
    configured = os.getenv("REDIS_HOST")
    if configured:
        return configured
    return "redis" if Path("/.dockerenv").exists() else "localhost"


@dataclass(frozen=True)
class RedisConfig:
    """Redis connection configuration."""

    host: str = field(default_factory=_default_redis_host)
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    password: str | None = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    socket_timeout: float = field(
        default_factory=lambda: float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0"))
    )
    decode_responses: bool = True

    @property
    def url(self) -> str:
        """Get Redis URL for connection."""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


@dataclass(frozen=True)
class SignalConfig:
    """Signal publishing configuration."""

    # Number of top liquidation zones to publish as signals
    top_n: int = field(default_factory=lambda: int(os.getenv("SIGNAL_TOP_N", "5")))

    # Feature flag to enable/disable signals
    enabled: bool = field(
        default_factory=lambda: os.getenv("SIGNALS_ENABLED", "true").lower() == "true"
    )

    # Redis channel prefix
    channel_prefix: str = "liquidation"

    # Rolling metric windows
    metric_windows: tuple[str, ...] = ("1h", "24h", "7d")

    # EMA smoothing factor for weight adjustment
    ema_alpha: float = field(default_factory=lambda: float(os.getenv("SIGNAL_EMA_ALPHA", "0.1")))

    # Minimum hit rate before rollback to defaults
    min_hit_rate: float = field(
        default_factory=lambda: float(os.getenv("SIGNAL_MIN_HIT_RATE", "0.50"))
    )


def get_signal_channel(
    symbol: str, channel_type: Literal["signals", "feedback"] = "signals"
) -> str:
    """Get Redis channel name for a symbol.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        channel_type: 'signals' for publishing, 'feedback' for consuming

    Returns:
        Channel name in format 'liquidation:{type}:{symbol}'
    """
    return f"liquidation:{channel_type}:{symbol}"


# Global config instances (lazy initialization)
_redis_config: RedisConfig | None = None
_signal_config: SignalConfig | None = None


def get_redis_config() -> RedisConfig:
    """Get Redis configuration (singleton)."""
    global _redis_config
    if _redis_config is None:
        _redis_config = RedisConfig()
    return _redis_config


def get_signal_config() -> SignalConfig:
    """Get signal configuration (singleton)."""
    global _signal_config
    if _signal_config is None:
        _signal_config = SignalConfig()
    return _signal_config
