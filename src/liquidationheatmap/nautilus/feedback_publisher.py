"""Redis feedback publisher for Nautilus-integrated execution paths.

This bridge closes the loop from downstream execution back into the adaptive
signal system by publishing TradeFeedback messages to the existing
`liquidation:feedback:{symbol}` channels.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.liquidationheatmap.signals.config import get_signal_channel
from src.liquidationheatmap.signals.models import TradeFeedback
from src.liquidationheatmap.signals.redis_client import RedisClient, get_redis_client

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NautilusFeedbackPublisher:
    """Publish execution feedback from Nautilus paths into Redis.

    This module intentionally does not depend on `nautilus_trader` so it can be
    tested in the current Python 3.10 environment and reused by mocked or native
    runtime integrations alike.
    """

    def __init__(
        self,
        redis_client: RedisClient | None = None,
        *,
        source: str = "nautilus",
    ) -> None:
        self._redis_client = redis_client
        self.source = source

    @property
    def redis_client(self) -> RedisClient:
        if self._redis_client is None:
            self._redis_client = get_redis_client()
        return self._redis_client

    def build_feedback(
        self,
        *,
        symbol: str,
        signal_id: str,
        entry_price: Decimal | float | int | str,
        exit_price: Decimal | float | int | str,
        pnl: Decimal | float | int | str,
        timestamp: datetime | None = None,
        source: str | None = None,
    ) -> TradeFeedback:
        """Build a TradeFeedback payload from execution data."""
        return TradeFeedback(
            symbol=symbol,
            signal_id=signal_id,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            timestamp=timestamp or _utc_now(),
            source=source or self.source,
        )

    def publish_feedback(self, feedback: TradeFeedback) -> bool:
        """Publish a pre-built TradeFeedback payload to Redis.

        Returns True when the publish call succeeded, even if zero subscribers
        were attached, and False only when the publish could not be performed.
        """
        channel = get_signal_channel(feedback.symbol, "feedback")
        result = self.redis_client.publish(channel, feedback.to_redis_message())
        if result is None:
            logger.warning(
                "Failed to publish Nautilus feedback for %s signal_id=%s",
                feedback.symbol,
                feedback.signal_id,
            )
            return False
        logger.debug(
            "Published Nautilus feedback to %s subscribers=%s signal_id=%s",
            channel,
            result,
            feedback.signal_id,
        )
        return True

    def publish_trade_feedback(
        self,
        *,
        symbol: str,
        signal_id: str,
        entry_price: Decimal | float | int | str,
        exit_price: Decimal | float | int | str,
        pnl: Decimal | float | int | str,
        timestamp: datetime | None = None,
        source: str | None = None,
    ) -> bool:
        """Build and publish a TradeFeedback payload in one step."""
        feedback = self.build_feedback(
            symbol=symbol,
            signal_id=signal_id,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            timestamp=timestamp,
            source=source,
        )
        return self.publish_feedback(feedback)
