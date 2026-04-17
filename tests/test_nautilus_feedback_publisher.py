from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

from src.liquidationheatmap.nautilus.feedback_publisher import NautilusFeedbackPublisher
from src.liquidationheatmap.signals.models import TradeFeedback


def test_build_feedback_creates_trade_feedback_with_defaults():
    publisher = NautilusFeedbackPublisher(redis_client=Mock())

    feedback = publisher.build_feedback(
        symbol="BTCUSDT",
        signal_id="sig-123",
        entry_price="95000.0",
        exit_price="95500.0",
        pnl="500.0",
    )

    assert isinstance(feedback, TradeFeedback)
    assert feedback.symbol == "BTCUSDT"
    assert feedback.signal_id == "sig-123"
    assert feedback.entry_price == Decimal("95000.0")
    assert feedback.exit_price == Decimal("95500.0")
    assert feedback.pnl == Decimal("500.0")
    assert feedback.source == "nautilus"
    assert feedback.timestamp.tzinfo == timezone.utc


def test_publish_feedback_uses_feedback_channel_and_payload():
    redis_client = Mock()
    redis_client.publish.return_value = 0
    publisher = NautilusFeedbackPublisher(redis_client=redis_client)
    feedback = TradeFeedback(
        symbol="BTCUSDT",
        signal_id="sig-123",
        entry_price="95000.0",
        exit_price="95500.0",
        pnl="500.0",
        timestamp=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        source="nautilus",
    )

    result = publisher.publish_feedback(feedback)

    assert result is True
    redis_client.publish.assert_called_once()
    channel, payload = redis_client.publish.call_args.args
    assert channel == "liquidation:feedback:BTCUSDT"
    assert '"signal_id":"sig-123"' in payload
    assert '"source":"nautilus"' in payload


def test_publish_trade_feedback_returns_false_when_redis_publish_fails():
    redis_client = Mock()
    redis_client.publish.return_value = None
    publisher = NautilusFeedbackPublisher(redis_client=redis_client)

    result = publisher.publish_trade_feedback(
        symbol="ETHUSDT",
        signal_id="sig-456",
        entry_price=2500.0,
        exit_price=2450.0,
        pnl=-50.0,
        timestamp=datetime(2026, 4, 17, 12, 30, tzinfo=timezone.utc),
    )

    assert result is False
    redis_client.publish.assert_called_once()
    channel, payload = redis_client.publish.call_args.args
    assert channel == "liquidation:feedback:ETHUSDT"
    assert '"signal_id":"sig-456"' in payload
    assert '"pnl":"-50.0"' in payload
