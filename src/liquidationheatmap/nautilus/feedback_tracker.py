"""Signal-to-feedback tracking helpers for Nautilus execution paths.

This module tracks which liquidation signal opened a position so downstream
position-close events can emit a precise TradeFeedback payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from src.liquidationheatmap.nautilus.feedback_publisher import NautilusFeedbackPublisher
from src.liquidationheatmap.signals.models import TradeFeedback


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TrackedSignal:
    symbol: str
    signal_id: str
    side: str
    entry_price: Decimal | None = None
    opened_at: datetime | None = None
    source: str = "nautilus"


class SignalFeedbackTracker:
    """Track signal lifecycle from entry intent to closed-position feedback."""

    def __init__(self, feedback_publisher: NautilusFeedbackPublisher | None = None) -> None:
        self.feedback_publisher = feedback_publisher or NautilusFeedbackPublisher()
        self._pending_by_symbol: dict[str, TrackedSignal] = {}
        self._active_by_symbol: dict[str, TrackedSignal] = {}

    def arm_signal(
        self,
        *,
        symbol: str,
        signal_id: str,
        side: str,
        source: str = "nautilus",
    ) -> None:
        self._pending_by_symbol[symbol] = TrackedSignal(
            symbol=symbol,
            signal_id=signal_id,
            side=side,
            source=source,
        )

    def pending_signal(self, symbol: str) -> TrackedSignal | None:
        return self._pending_by_symbol.get(symbol)

    def active_signal(self, symbol: str) -> TrackedSignal | None:
        return self._active_by_symbol.get(symbol)

    def mark_entry(
        self,
        *,
        symbol: str,
        entry_price: Decimal | float | int | str,
        opened_at: datetime | None = None,
    ) -> TrackedSignal | None:
        tracked = self._pending_by_symbol.pop(symbol, None)
        if tracked is None:
            return None
        tracked.entry_price = Decimal(str(entry_price))
        tracked.opened_at = opened_at or _utc_now()
        self._active_by_symbol[symbol] = tracked
        return tracked

    def clear_symbol(self, symbol: str) -> None:
        self._pending_by_symbol.pop(symbol, None)
        self._active_by_symbol.pop(symbol, None)

    def build_close_feedback(
        self,
        *,
        symbol: str,
        exit_price: Decimal | float | int | str,
        pnl: Decimal | float | int | str,
        closed_at: datetime | None = None,
    ) -> TradeFeedback | None:
        tracked = self._active_by_symbol.get(symbol)
        if tracked is None or tracked.entry_price is None:
            return None
        return self.feedback_publisher.build_feedback(
            symbol=symbol,
            signal_id=tracked.signal_id,
            entry_price=tracked.entry_price,
            exit_price=exit_price,
            pnl=pnl,
            timestamp=closed_at or _utc_now(),
            source=tracked.source,
        )

    def publish_close_feedback(
        self,
        *,
        symbol: str,
        exit_price: Decimal | float | int | str,
        pnl: Decimal | float | int | str,
        closed_at: datetime | None = None,
    ) -> bool:
        feedback = self.build_close_feedback(
            symbol=symbol,
            exit_price=exit_price,
            pnl=pnl,
            closed_at=closed_at,
        )
        if feedback is None:
            return False
        published = self.feedback_publisher.publish_feedback(feedback)
        if published:
            self._active_by_symbol.pop(symbol, None)
        return published
