"""Adaptive Signal Loop module for real-time liquidation signals.

This module provides:
- SignalPublisher: Publishes top liquidation zones to Redis
- FeedbackConsumer: Consumes P&L feedback from Nautilus
- AdaptiveEngine: Adjusts weights based on rolling accuracy

Redis Channels:
- liquidation:signals:{symbol} - Signal output
- liquidation:feedback:{symbol} - P&L feedback input
"""

from src.liquidationheatmap.signals.adaptive import (
    AdaptiveEngine,
    calculate_ema,
)
from src.liquidationheatmap.signals.config import (
    RedisConfig,
    SignalConfig,
    get_redis_config,
    get_signal_channel,
    get_signal_config,
)
from src.liquidationheatmap.signals.feedback import (
    ContinuousReportUnavailableError,
    FeedbackConsumer,
    FeedbackDBService,
    load_continuous_runtime_snapshot,
)
from src.liquidationheatmap.signals.models import (
    ContinuousReport,
    LiquidationSignal,
    SignalMetrics,
    SignalStatus,
    TradeFeedback,
)
from src.liquidationheatmap.signals.publisher import (
    SignalPublisher,
    get_publisher,
    publish_signals_from_snapshot,
)
from src.liquidationheatmap.signals.redis_client import (
    RedisClient,
    close_redis_client,
    get_redis_client,
)

__all__ = [
    # Models
    "LiquidationSignal",
    "TradeFeedback",
    "SignalMetrics",
    "SignalStatus",
    "ContinuousReport",
    # Config
    "RedisConfig",
    "SignalConfig",
    "get_redis_config",
    "get_signal_config",
    "get_signal_channel",
    # Redis
    "RedisClient",
    "get_redis_client",
    "close_redis_client",
    # Publisher
    "SignalPublisher",
    "get_publisher",
    "publish_signals_from_snapshot",
    # Feedback
    "FeedbackConsumer",
    "FeedbackDBService",
    "ContinuousReportUnavailableError",
    "load_continuous_runtime_snapshot",
    # Adaptive
    "AdaptiveEngine",
    "calculate_ema",
]
