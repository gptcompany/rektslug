from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

from src.liquidationheatmap.nautilus.feedback_tracker import SignalFeedbackTracker
from src.liquidationheatmap.signals.models import TradeFeedback


def test_mark_entry_promotes_pending_signal_to_active():
    tracker = SignalFeedbackTracker(feedback_publisher=Mock())

    tracker.arm_signal(symbol="BTCUSDT", signal_id="sig-1", side="long")
    tracked = tracker.mark_entry(
        symbol="BTCUSDT",
        entry_price="95000.5",
        opened_at=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert tracked is not None
    assert tracked.signal_id == "sig-1"
    assert tracked.entry_price == Decimal("95000.5")
    assert tracker.pending_signal("BTCUSDT") is None
    assert tracker.active_signal("BTCUSDT") is tracked


def test_build_close_feedback_uses_active_signal_context():
    feedback_publisher = Mock()
    feedback_publisher.build_feedback.return_value = TradeFeedback(
        symbol="BTCUSDT",
        signal_id="sig-1",
        entry_price="95000.5",
        exit_price="95500.0",
        pnl="499.5",
        timestamp=datetime(2026, 4, 17, 13, 0, tzinfo=timezone.utc),
        source="nautilus",
    )
    tracker = SignalFeedbackTracker(feedback_publisher=feedback_publisher)
    tracker.arm_signal(symbol="BTCUSDT", signal_id="sig-1", side="long")
    tracker.mark_entry(symbol="BTCUSDT", entry_price="95000.5")

    feedback = tracker.build_close_feedback(
        symbol="BTCUSDT",
        exit_price="95500.0",
        pnl="499.5",
        closed_at=datetime(2026, 4, 17, 13, 0, tzinfo=timezone.utc),
    )

    assert isinstance(feedback, TradeFeedback)
    feedback_publisher.build_feedback.assert_called_once()
    kwargs = feedback_publisher.build_feedback.call_args.kwargs
    assert kwargs["signal_id"] == "sig-1"
    assert kwargs["entry_price"] == Decimal("95000.5")
    assert kwargs["exit_price"] == "95500.0"


def test_publish_close_feedback_clears_active_signal_on_success():
    feedback = TradeFeedback(
        symbol="BTCUSDT",
        signal_id="sig-1",
        entry_price="95000.5",
        exit_price="95500.0",
        pnl="499.5",
        timestamp=datetime(2026, 4, 17, 13, 0, tzinfo=timezone.utc),
        source="nautilus",
    )
    feedback_publisher = Mock()
    feedback_publisher.build_feedback.return_value = feedback
    feedback_publisher.publish_feedback.return_value = True
    tracker = SignalFeedbackTracker(feedback_publisher=feedback_publisher)
    tracker.arm_signal(symbol="BTCUSDT", signal_id="sig-1", side="long")
    tracker.mark_entry(symbol="BTCUSDT", entry_price="95000.5")

    result = tracker.publish_close_feedback(
        symbol="BTCUSDT",
        exit_price="95500.0",
        pnl="499.5",
    )

    assert result is True
    feedback_publisher.publish_feedback.assert_called_once_with(feedback)
    assert tracker.active_signal("BTCUSDT") is None


def test_publish_close_feedback_returns_false_without_active_signal():
    feedback_publisher = Mock()
    tracker = SignalFeedbackTracker(feedback_publisher=feedback_publisher)

    result = tracker.publish_close_feedback(
        symbol="ETHUSDT",
        exit_price="2450.0",
        pnl="-50.0",
    )

    assert result is False
    feedback_publisher.publish_feedback.assert_not_called()
