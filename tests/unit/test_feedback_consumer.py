"""Unit tests for FeedbackConsumer.

TDD RED Phase: Tests written before implementation.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.liquidationheatmap.signals.models import TradeFeedback


class TestTradeFeedbackModel:
    """Tests for TradeFeedback Pydantic model."""

    def test_feedback_creation_with_valid_data(self):
        """Feedback should be created with valid data."""
        feedback = TradeFeedback(
            symbol="BTCUSDT",
            signal_id="abc123",
            entry_price=Decimal("95000.00"),
            exit_price=Decimal("95500.00"),
            pnl=Decimal("500.00"),
            source="nautilus",
        )
        assert feedback.symbol == "BTCUSDT"
        assert feedback.signal_id == "abc123"
        assert feedback.entry_price == Decimal("95000.00")
        assert feedback.exit_price == Decimal("95500.00")
        assert feedback.pnl == Decimal("500.00")
        assert feedback.source == "nautilus"

    def test_feedback_price_converts_from_float(self):
        """Prices should convert from float to Decimal."""
        feedback = TradeFeedback(
            symbol="BTCUSDT",
            signal_id="abc123",
            entry_price=95000.50,
            exit_price=95500.25,
            pnl=499.75,
            source="nautilus",
        )
        assert isinstance(feedback.entry_price, Decimal)
        assert isinstance(feedback.exit_price, Decimal)
        assert isinstance(feedback.pnl, Decimal)

    def test_feedback_is_profitable_positive_pnl(self):
        """is_profitable should return True for positive P&L."""
        feedback = TradeFeedback(
            symbol="BTCUSDT",
            signal_id="abc123",
            entry_price=95000,
            exit_price=95500,
            pnl=500,
            source="nautilus",
        )
        assert feedback.is_profitable is True

    def test_feedback_is_profitable_negative_pnl(self):
        """is_profitable should return False for negative P&L."""
        feedback = TradeFeedback(
            symbol="BTCUSDT",
            signal_id="abc123",
            entry_price=95000,
            exit_price=94500,
            pnl=-500,
            source="nautilus",
        )
        assert feedback.is_profitable is False

    def test_feedback_pnl_pct_calculation(self):
        """pnl_pct should calculate percentage correctly."""
        feedback = TradeFeedback(
            symbol="BTCUSDT",
            signal_id="abc123",
            entry_price=100000,
            exit_price=101000,
            pnl=1000,
            source="nautilus",
        )
        assert feedback.pnl_pct == pytest.approx(1.0, rel=0.01)  # 1%

    def test_feedback_source_validation(self):
        """Source must be 'nautilus' or 'manual'."""
        with pytest.raises(ValueError):
            TradeFeedback(
                symbol="BTCUSDT",
                signal_id="abc123",
                entry_price=95000,
                exit_price=95500,
                pnl=500,
                source="invalid",  # Invalid source
            )

    def test_feedback_serialization_to_redis(self):
        """Feedback should serialize to JSON for Redis."""
        feedback = TradeFeedback(
            symbol="BTCUSDT",
            signal_id="abc123",
            entry_price=Decimal("95000.00"),
            exit_price=Decimal("95500.00"),
            pnl=Decimal("500.00"),
            timestamp=datetime(2025, 12, 28, 11, 0, 0),
            source="nautilus",
        )
        json_str = feedback.to_redis_message()
        assert '"symbol":"BTCUSDT"' in json_str
        assert '"signal_id":"abc123"' in json_str
        assert '"source":"nautilus"' in json_str

    def test_feedback_deserialization_from_redis(self):
        """Feedback should deserialize from Redis JSON message."""
        json_str = '{"symbol":"BTCUSDT","signal_id":"abc123","entry_price":"95000.00","exit_price":"95500.00","pnl":"500.00","timestamp":"2025-12-28T11:00:00","source":"nautilus"}'
        feedback = TradeFeedback.from_redis_message(json_str)
        assert feedback.symbol == "BTCUSDT"
        assert feedback.signal_id == "abc123"
        assert feedback.pnl == Decimal("500.00")
        assert feedback.source == "nautilus"


class TestFeedbackConsumer:
    """Tests for FeedbackConsumer class."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client."""
        mock = MagicMock()
        mock.is_connected = True
        return mock

    @pytest.fixture
    def mock_db_service(self):
        """Create mock DuckDB service."""
        mock = MagicMock()
        mock.store_feedback.return_value = True
        return mock

    def test_consumer_initialization(self, mock_redis_client):
        """Consumer should initialize with Redis client."""
        from src.liquidationheatmap.signals.feedback import FeedbackConsumer

        with patch(
            "src.liquidationheatmap.signals.feedback.get_redis_client",
            return_value=mock_redis_client,
        ):
            consumer = FeedbackConsumer()
            assert consumer is not None

    def test_store_feedback_calls_duckdb(self, mock_redis_client, mock_db_service):
        """store_feedback should insert into DuckDB."""
        from src.liquidationheatmap.signals.feedback import FeedbackConsumer

        with patch(
            "src.liquidationheatmap.signals.feedback.get_redis_client",
            return_value=mock_redis_client,
        ):
            consumer = FeedbackConsumer(db_service=mock_db_service)

            feedback = TradeFeedback(
                symbol="BTCUSDT",
                signal_id="abc123",
                entry_price=95000,
                exit_price=95500,
                pnl=500,
                source="nautilus",
            )

            result = consumer.store_feedback(feedback)

            assert result is True
            mock_db_service.store_feedback.assert_called_once()

    def test_process_message_parses_json(self, mock_redis_client, mock_db_service):
        """process_message should parse JSON and store feedback."""
        from src.liquidationheatmap.signals.feedback import FeedbackConsumer

        with patch(
            "src.liquidationheatmap.signals.feedback.get_redis_client",
            return_value=mock_redis_client,
        ):
            consumer = FeedbackConsumer(db_service=mock_db_service)

            message = {
                "type": "message",
                "channel": "liquidation:feedback:BTCUSDT",
                "data": '{"symbol":"BTCUSDT","signal_id":"abc123","entry_price":"95000","exit_price":"95500","pnl":"500","timestamp":"2025-12-28T11:00:00","source":"nautilus"}',
            }

            result = consumer.process_message(message)

            assert result is True
            mock_db_service.store_feedback.assert_called_once()

    def test_process_message_handles_invalid_json(self, mock_redis_client, mock_db_service):
        """process_message should handle invalid JSON gracefully."""
        from src.liquidationheatmap.signals.feedback import FeedbackConsumer

        with patch(
            "src.liquidationheatmap.signals.feedback.get_redis_client",
            return_value=mock_redis_client,
        ):
            consumer = FeedbackConsumer(db_service=mock_db_service)

            message = {
                "type": "message",
                "channel": "liquidation:feedback:BTCUSDT",
                "data": "not valid json",
            }

            result = consumer.process_message(message)

            assert result is False
            mock_db_service.store_feedback.assert_not_called()

    def test_process_message_handles_malformed_feedback(self, mock_redis_client, mock_db_service):
        """process_message should handle malformed feedback gracefully."""
        from src.liquidationheatmap.signals.feedback import FeedbackConsumer

        with patch(
            "src.liquidationheatmap.signals.feedback.get_redis_client",
            return_value=mock_redis_client,
        ):
            consumer = FeedbackConsumer(db_service=mock_db_service)

            # Missing required fields
            message = {
                "type": "message",
                "channel": "liquidation:feedback:BTCUSDT",
                "data": '{"symbol":"BTCUSDT"}',
            }

            result = consumer.process_message(message)

            assert result is False
            mock_db_service.store_feedback.assert_not_called()

    def test_subscribe_feedback_uses_correct_channel(self, mock_redis_client):
        """subscribe_feedback should subscribe to correct channel."""
        from src.liquidationheatmap.signals.feedback import FeedbackConsumer

        mock_pubsub = MagicMock()
        mock_redis_client.pubsub.return_value.__enter__ = MagicMock(return_value=mock_pubsub)
        mock_redis_client.pubsub.return_value.__exit__ = MagicMock(return_value=None)
        mock_pubsub.listen.return_value = iter([])  # Empty iterator

        with patch(
            "src.liquidationheatmap.signals.feedback.get_redis_client",
            return_value=mock_redis_client,
        ):
            consumer = FeedbackConsumer()
            consumer.subscribe_feedback("BTCUSDT", timeout=0.0)

            # Verify subscribe was called with correct channel
            mock_pubsub.subscribe.assert_called_once_with("liquidation:feedback:BTCUSDT")

    def test_subscribe_multiple_symbols(self, mock_redis_client):
        """always-on consumer should support multiple symbols."""
        from src.liquidationheatmap.signals.feedback import FeedbackConsumer

        mock_pubsub = MagicMock()
        mock_redis_client.pubsub.return_value.__enter__ = MagicMock(return_value=mock_pubsub)
        mock_redis_client.pubsub.return_value.__exit__ = MagicMock(return_value=None)
        mock_pubsub.listen.return_value = iter([])

        with patch(
            "src.liquidationheatmap.signals.feedback.get_redis_client",
            return_value=mock_redis_client,
        ):
            consumer = FeedbackConsumer()
            consumer.subscribe_feedback(["BTCUSDT", "ETHUSDT"], timeout=0.0)

            # Verify subscribe was called with multiple channels
            mock_pubsub.subscribe.assert_called_once_with(
                "liquidation:feedback:BTCUSDT",
                "liquidation:feedback:ETHUSDT"
            )

    def test_subscribe_handles_connection_error(self, mock_redis_client):
        """always-on consumer should handle redis connection errors and continue/reconnect."""
        from src.liquidationheatmap.signals.feedback import FeedbackConsumer
        from redis.exceptions import ConnectionError

        mock_pubsub = MagicMock()
        mock_redis_client.pubsub.return_value.__enter__ = MagicMock(return_value=mock_pubsub)
        mock_redis_client.pubsub.return_value.__exit__ = MagicMock(return_value=None)
        
        # Make listen raise a connection error on first call, then KeyboardInterrupt on second to exit gracefully
        mock_pubsub.listen.side_effect = [ConnectionError("Redis down"), KeyboardInterrupt("Stop test")]

        with patch(
            "src.liquidationheatmap.signals.feedback.get_redis_client",
            return_value=mock_redis_client,
        ) as mock_get_client, patch("time.sleep") as mock_sleep:
            consumer = FeedbackConsumer()
            # Should not raise exception
            consumer.subscribe_feedback("BTCUSDT")
            
            # Should have called listen twice (reconnected and then interrupted)
            assert mock_pubsub.listen.call_count == 2
            # Should have slept before reconnecting
            mock_sleep.assert_called_once_with(5)

    def test_consumer_persistence_accounting(self, mock_redis_client, mock_db_service):
        """Consumer should track the number of successfully persisted feedback messages."""
        from src.liquidationheatmap.signals.feedback import FeedbackConsumer

        with patch(
            "src.liquidationheatmap.signals.feedback.get_redis_client",
            return_value=mock_redis_client,
        ):
            consumer = FeedbackConsumer(db_service=mock_db_service)
            
            # Initial count should be 0
            assert consumer.persisted_count == 0
            
            # Successful storage should increment count
            mock_db_service.store_feedback.return_value = True
            consumer.process_message({
                "type": "message",
                "channel": "liquidation:feedback:BTCUSDT",
                "data": '{"symbol":"BTCUSDT","signal_id":"1","entry_price":"1","exit_price":"2","pnl":"1","timestamp":"2025-12-28T11:00:00","source":"nautilus"}'
            })
            assert consumer.persisted_count == 1
            
            # Failed storage should not increment count
            mock_db_service.store_feedback.return_value = False
            consumer.process_message({
                "type": "message",
                "channel": "liquidation:feedback:BTCUSDT",
                "data": '{"symbol":"BTCUSDT","signal_id":"2","entry_price":"1","exit_price":"2","pnl":"1","timestamp":"2025-12-28T11:00:00","source":"nautilus"}'
            })
            assert consumer.persisted_count == 1
