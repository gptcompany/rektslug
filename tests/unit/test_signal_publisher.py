"""Unit tests for SignalPublisher.

TDD RED Phase: Tests written before implementation.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.liquidationheatmap.signals.models import LiquidationSignal


class TestLiquidationSignalModel:
    """Tests for LiquidationSignal Pydantic model."""

    def test_signal_creation_with_valid_data(self):
        """Signal should be created with valid data."""
        signal = LiquidationSignal(
            symbol="BTCUSDT",
            price=Decimal("95000.50"),
            side="long",
            confidence=0.85,
        )
        assert signal.symbol == "BTCUSDT"
        assert signal.price == Decimal("95000.50")
        assert signal.side == "long"
        assert signal.confidence == 0.85
        assert signal.source == "liquidationheatmap"

    def test_signal_price_converts_from_float(self):
        """Price should convert from float to Decimal."""
        signal = LiquidationSignal(
            symbol="BTCUSDT",
            price=95000.50,
            side="long",
            confidence=0.85,
        )
        assert isinstance(signal.price, Decimal)
        assert signal.price == Decimal("95000.5")

    def test_signal_price_converts_from_string(self):
        """Price should convert from string to Decimal."""
        signal = LiquidationSignal(
            symbol="BTCUSDT",
            price="95000.50",
            side="short",
            confidence=0.5,
        )
        assert isinstance(signal.price, Decimal)
        assert signal.price == Decimal("95000.50")

    def test_signal_confidence_range_validation(self):
        """Confidence must be between 0.0 and 1.0."""
        with pytest.raises(ValueError):
            LiquidationSignal(
                symbol="BTCUSDT",
                price=95000,
                side="long",
                confidence=1.5,  # Invalid: > 1.0
            )

    def test_signal_side_validation(self):
        """Side must be 'long' or 'short'."""
        with pytest.raises(ValueError):
            LiquidationSignal(
                symbol="BTCUSDT",
                price=95000,
                side="invalid",  # Invalid side
                confidence=0.5,
            )

    def test_signal_serialization_to_redis(self):
        """Signal should serialize to JSON for Redis."""
        signal = LiquidationSignal(
            symbol="BTCUSDT",
            price=Decimal("95000.50"),
            side="long",
            confidence=0.85,
            timestamp=datetime(2025, 12, 28, 10, 30, 0),
        )
        json_str = signal.to_redis_message()
        assert '"symbol":"BTCUSDT"' in json_str
        assert '"price":"95000.50"' in json_str
        assert '"side":"long"' in json_str

    def test_signal_deserialization_from_redis(self):
        """Signal should deserialize from Redis JSON message."""
        json_str = '{"symbol":"BTCUSDT","price":"95000.50","side":"long","confidence":0.85,"timestamp":"2025-12-28T10:30:00","source":"liquidationheatmap","signal_id":null}'
        signal = LiquidationSignal.from_redis_message(json_str)
        assert signal.symbol == "BTCUSDT"
        assert signal.price == Decimal("95000.50")
        assert signal.side == "long"
        assert signal.confidence == 0.85


class TestSignalPublisher:
    """Tests for SignalPublisher class."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client."""
        mock = MagicMock()
        mock.is_connected = True
        mock.publish.return_value = 1
        return mock

    def test_publisher_initialization(self, mock_redis_client):
        """Publisher should initialize with Redis client."""
        from src.liquidationheatmap.signals.publisher import SignalPublisher

        with patch(
            "src.liquidationheatmap.signals.publisher.get_redis_client",
            return_value=mock_redis_client,
        ):
            publisher = SignalPublisher()
            assert publisher is not None

    def test_publish_signal_calls_redis(self, mock_redis_client):
        """publish_signal should call Redis publish."""
        from src.liquidationheatmap.signals.publisher import SignalPublisher

        with patch(
            "src.liquidationheatmap.signals.publisher.get_redis_client",
            return_value=mock_redis_client,
        ):
            publisher = SignalPublisher()
            result = publisher.publish_signal(
                symbol="BTCUSDT",
                price=95000.50,
                side="long",
                confidence=0.85,
            )

            assert result is True
            mock_redis_client.publish.assert_called_once()
            call_args = mock_redis_client.publish.call_args
            assert "liquidation:signals:BTCUSDT" in call_args[0]

    def test_publish_signal_graceful_failure(self, mock_redis_client):
        """publish_signal should return False when Redis unavailable."""
        mock_redis_client.publish.return_value = None

        from src.liquidationheatmap.signals.publisher import SignalPublisher

        with patch(
            "src.liquidationheatmap.signals.publisher.get_redis_client",
            return_value=mock_redis_client,
        ):
            publisher = SignalPublisher()
            result = publisher.publish_signal(
                symbol="BTCUSDT",
                price=95000.50,
                side="long",
                confidence=0.85,
            )

            assert result is False

    def test_publish_signal_records_persisted_status_metrics(self, mock_redis_client):
        """Successful publish should persist last-publish and rolling 24h metrics."""
        from src.liquidationheatmap.signals.publisher import SignalPublisher

        raw_backend = MagicMock()
        mock_redis_client.connect.return_value = raw_backend

        with patch(
            "src.liquidationheatmap.signals.publisher.get_redis_client",
            return_value=mock_redis_client,
        ):
            publisher = SignalPublisher()
            result = publisher.publish_signal(
                symbol="BTCUSDT",
                price=95000.50,
                side="long",
                confidence=0.85,
                signal_id="sig-1",
            )

            assert result is True
            raw_backend.set.assert_called_once()
            raw_backend.zadd.assert_called_once()
            raw_backend.zremrangebyscore.assert_called_once()

    def test_extract_top_signals_returns_list(self):
        """extract_top_signals should return list of signals."""
        from src.liquidationheatmap.signals.publisher import SignalPublisher

        # Mock heatmap data with zones
        heatmap_data = {
            "zones": [
                {"price": 95000, "intensity": 0.9, "side": "long"},
                {"price": 94500, "intensity": 0.7, "side": "long"},
                {"price": 96000, "intensity": 0.8, "side": "short"},
                {"price": 93000, "intensity": 0.5, "side": "long"},
                {"price": 97000, "intensity": 0.6, "side": "short"},
                {"price": 92000, "intensity": 0.3, "side": "long"},
            ]
        }

        with patch(
            "src.liquidationheatmap.signals.publisher.get_redis_client",
            return_value=MagicMock(),
        ):
            publisher = SignalPublisher()
            signals = publisher.extract_top_signals(
                symbol="BTCUSDT",
                heatmap_data=heatmap_data,
                top_n=5,
            )

            assert len(signals) == 5
            # Should be sorted by intensity (highest first)
            assert signals[0].confidence == 0.9
            assert signals[0].price == Decimal("95000")

    def test_extract_top_signals_respects_top_n(self):
        """extract_top_signals should respect SIGNAL_TOP_N config."""
        from src.liquidationheatmap.signals.publisher import SignalPublisher

        heatmap_data = {
            "zones": [
                {"price": 95000, "intensity": 0.9, "side": "long"},
                {"price": 94500, "intensity": 0.7, "side": "long"},
                {"price": 96000, "intensity": 0.8, "side": "short"},
            ]
        }

        with patch(
            "src.liquidationheatmap.signals.publisher.get_redis_client",
            return_value=MagicMock(),
        ):
            publisher = SignalPublisher()
            signals = publisher.extract_top_signals(
                symbol="BTCUSDT",
                heatmap_data=heatmap_data,
                top_n=2,
            )

            assert len(signals) == 2

    def test_extract_top_signals_handles_empty_zones(self):
        """extract_top_signals should handle empty heatmap data."""
        from src.liquidationheatmap.signals.publisher import SignalPublisher

        heatmap_data = {"zones": []}

        with patch(
            "src.liquidationheatmap.signals.publisher.get_redis_client",
            return_value=MagicMock(),
        ):
            publisher = SignalPublisher()
            signals = publisher.extract_top_signals(
                symbol="BTCUSDT",
                heatmap_data=heatmap_data,
                top_n=5,
            )

            assert len(signals) == 0

    def test_extract_top_signals_skips_invalid_prices(self):
        """extract_top_signals should skip zones with invalid prices.

        Edge case: Zones with price=0, missing price, or negative price
        should be skipped gracefully instead of raising ValidationError.
        """
        from src.liquidationheatmap.signals.publisher import SignalPublisher

        heatmap_data = {
            "zones": [
                {"price": 0, "intensity": 0.9, "side": "long"},  # Invalid: zero
                {"intensity": 0.8, "side": "short"},  # Invalid: missing (defaults to 0)
                {"price": 95000, "intensity": 0.7, "side": "long"},  # Valid
                {"price": -100, "intensity": 0.6, "side": "short"},  # Invalid: negative
                {"price": 94500, "intensity": 0.5, "side": "long"},  # Valid
            ]
        }

        with patch(
            "src.liquidationheatmap.signals.publisher.get_redis_client",
            return_value=MagicMock(),
        ):
            publisher = SignalPublisher()
            signals = publisher.extract_top_signals(
                symbol="BTCUSDT",
                heatmap_data=heatmap_data,
                top_n=10,
            )

            # Only 2 valid zones should be extracted
            assert len(signals) == 2
            prices = [s.price for s in signals]
            assert Decimal("95000") in prices
            assert Decimal("94500") in prices


class TestSignalPublisherIntegrationPoints:
    """Tests for SignalPublisher integration with heatmap calculation."""

    def test_publish_batch_publishes_multiple_signals(self):
        """publish_batch should publish multiple signals."""
        from src.liquidationheatmap.signals.publisher import SignalPublisher

        mock_client = MagicMock()
        mock_client.publish.return_value = 1

        with patch(
            "src.liquidationheatmap.signals.publisher.get_redis_client",
            return_value=mock_client,
        ):
            publisher = SignalPublisher()

            signals = [
                LiquidationSignal(symbol="BTCUSDT", price=95000, side="long", confidence=0.9),
                LiquidationSignal(symbol="BTCUSDT", price=94500, side="long", confidence=0.7),
            ]

            result = publisher.publish_batch(signals)
            assert result == 2
            assert mock_client.publish.call_count == 2
