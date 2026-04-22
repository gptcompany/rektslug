"""Integration tests for Redis pub/sub.

These tests require a running Redis server.
Skip if Redis is not available.

TDD RED Phase: Tests written before implementation.
"""

import time
from decimal import Decimal
from threading import Thread

import pytest

from src.liquidationheatmap.signals.models import LiquidationSignal

# Skip all tests if Redis is not available
try:
    import redis

    r = redis.Redis(host="localhost", port=6379, socket_timeout=1)
    r.ping()
    REDIS_AVAILABLE = True
except Exception:
    REDIS_AVAILABLE = False


@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
class TestRedisConnection:
    """Tests for Redis connection manager."""

    def test_redis_client_connects(self):
        """Redis client should connect successfully."""
        from src.liquidationheatmap.signals.redis_client import RedisClient

        client = RedisClient()
        try:
            assert client.is_connected or client.connect() is not None
        finally:
            client.disconnect()

    def test_redis_client_ping(self):
        """Redis client should respond to ping."""
        from src.liquidationheatmap.signals.redis_client import RedisClient

        client = RedisClient()
        try:
            conn = client.connect()
            assert conn is not None
            assert conn.ping() is True
        finally:
            client.disconnect()

    def test_redis_graceful_fallback(self):
        """Redis client should handle connection failure gracefully."""
        from src.liquidationheatmap.signals.config import RedisConfig
        from src.liquidationheatmap.signals.redis_client import RedisClient

        # Use invalid port to simulate connection failure
        config = RedisConfig(
            host="localhost",
            port=9999,  # Invalid port
            socket_timeout=1.0,
        )
        client = RedisClient(config=config)
        result = client.connect()
        assert result is None  # Graceful fallback
        assert client.is_connected is False


@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
class TestRedisPubSub:
    """Tests for Redis pub/sub operations."""

    def test_publish_message(self):
        """Should publish message to Redis channel."""
        from src.liquidationheatmap.signals.redis_client import RedisClient

        client = RedisClient()
        try:
            # Publish returns number of subscribers (0 if none)
            result = client.publish("test:channel", '{"test": "data"}')
            assert result is not None
            assert isinstance(result, int)
        finally:
            client.disconnect()

    def test_pubsub_receive_message(self):
        """Should receive message via pub/sub."""
        from src.liquidationheatmap.signals.redis_client import RedisClient

        client = RedisClient()
        received_messages = []

        def subscriber():
            with client.pubsub() as ps:
                if ps is None:
                    return
                ps.subscribe("test:pubsub")
                # Wait for subscription confirmation
                for msg in ps.listen():
                    if msg["type"] == "subscribe":
                        continue
                    if msg["type"] == "message":
                        received_messages.append(msg["data"])
                        break

        try:
            # Start subscriber in background
            thread = Thread(target=subscriber, daemon=True)
            thread.start()

            # Give subscriber time to connect
            time.sleep(0.2)

            # Publish message
            client.publish("test:pubsub", "test_message")

            # Wait for message
            thread.join(timeout=2.0)

            assert len(received_messages) == 1
            assert received_messages[0] == "test_message"
        finally:
            client.disconnect()

    def test_blocking_pubsub_does_not_drop_subscription_on_socket_timeout(self):
        """Blocking pubsub should stay subscribed past the default socket timeout."""
        from src.liquidationheatmap.signals.config import RedisConfig
        from src.liquidationheatmap.signals.redis_client import RedisClient

        config = RedisConfig(host="localhost", port=6379, db=0, socket_timeout=0.2)
        client = RedisClient(config=config)
        publisher = RedisClient(config=config)
        received_messages = []

        def subscriber():
            with client.pubsub(blocking=True) as ps:
                if ps is None:
                    return
                ps.subscribe("test:pubsub:blocking")
                for msg in ps.listen():
                    if msg["type"] == "subscribe":
                        continue
                    if msg["type"] == "message":
                        received_messages.append(msg["data"])
                        break

        try:
            thread = Thread(target=subscriber, daemon=True)
            thread.start()

            # Publish well after the standard socket_timeout window.
            time.sleep(0.6)
            publisher.publish("test:pubsub:blocking", "delayed_message")

            thread.join(timeout=2.0)

            assert received_messages == ["delayed_message"]
        finally:
            client.disconnect()
            publisher.disconnect()


@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
class TestSignalPublisherIntegration:
    """Integration tests for SignalPublisher with real Redis."""

    def test_publish_signal_to_redis(self):
        """SignalPublisher should publish signal to Redis."""
        from src.liquidationheatmap.signals.publisher import SignalPublisher

        publisher = SignalPublisher()
        received_messages = []

        def subscriber():
            from src.liquidationheatmap.signals.redis_client import RedisClient

            client = RedisClient()
            with client.pubsub() as ps:
                if ps is None:
                    return
                ps.subscribe("liquidation:signals:BTCUSDT")
                for msg in ps.listen():
                    if msg["type"] == "subscribe":
                        continue
                    if msg["type"] == "message":
                        received_messages.append(msg["data"])
                        break

        try:
            # Start subscriber
            thread = Thread(target=subscriber, daemon=True)
            thread.start()
            time.sleep(0.2)

            # Publish signal
            result = publisher.publish_signal(
                symbol="BTCUSDT",
                price=95000.50,
                side="long",
                confidence=0.85,
            )

            # Wait for message
            thread.join(timeout=2.0)

            assert result is True
            assert len(received_messages) == 1

            # Verify message content
            signal = LiquidationSignal.from_redis_message(received_messages[0])
            assert signal.symbol == "BTCUSDT"
            assert signal.price == Decimal("95000.5")
            assert signal.side == "long"
            assert signal.confidence == 0.85
        finally:
            publisher.close()

    def test_publish_latency_under_10ms(self):
        """Signal publish should complete in under 10ms."""
        import time

        from src.liquidationheatmap.signals.publisher import SignalPublisher

        publisher = SignalPublisher()

        try:
            # Warm up connection
            publisher.publish_signal("BTCUSDT", 95000, "long", 0.5)

            # Measure latency
            start = time.perf_counter()
            publisher.publish_signal("BTCUSDT", 95000, "long", 0.5)
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert elapsed_ms < 10, f"Publish took {elapsed_ms:.2f}ms, expected <10ms"
        finally:
            publisher.close()

    def test_publish_batch_performance(self):
        """Batch publish should complete efficiently."""
        import time

        from src.liquidationheatmap.signals.publisher import SignalPublisher

        publisher = SignalPublisher()

        signals = [
            LiquidationSignal(
                symbol="BTCUSDT",
                price=95000 + i * 100,
                side="long" if i % 2 == 0 else "short",
                confidence=0.9 - i * 0.1,
            )
            for i in range(5)
        ]

        try:
            start = time.perf_counter()
            count = publisher.publish_batch(signals)
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert count == 5
            # 5 signals should complete in under 50ms
            assert elapsed_ms < 50, f"Batch publish took {elapsed_ms:.2f}ms"
        finally:
            publisher.close()
