"""Redis connection manager for Adaptive Signal Loop.

Provides thread-safe Redis connection with graceful fallback per Constitution Section 6.
"""

import logging
from contextlib import contextmanager
from threading import Lock
from typing import Any, Callable, Generator

import redis
from redis.exceptions import ConnectionError, TimeoutError

from src.liquidationheatmap.signals.config import RedisConfig, get_redis_config

logger = logging.getLogger(__name__)
_UNSET = object()


class RedisConnectionError(Exception):
    """Raised when Redis connection fails."""

    pass


class RedisClient:
    """Thread-safe Redis client with graceful fallback.

    Features:
    - Lazy connection (connects on first use)
    - Connection pooling
    - Graceful degradation (logs warning, continues without Redis)
    - Pub/sub support

    Usage:
        client = RedisClient()
        client.publish("channel", "message")

        # Or with context manager
        with client.pubsub() as ps:
            ps.subscribe("channel")
            for message in ps.listen():
                print(message)
    """

    def __init__(self, config: RedisConfig | None = None):
        """Initialize Redis client.

        Args:
            config: Redis configuration (uses global config if None)
        """
        self.config = config or get_redis_config()
        self._pool: redis.ConnectionPool | None = None
        self._client: redis.Redis | None = None
        self._lock = Lock()
        self._connected = False

    def _create_pool(self, socket_timeout: float | None | object = _UNSET) -> redis.ConnectionPool:
        """Create Redis connection pool."""
        timeout = self.config.socket_timeout if socket_timeout is _UNSET else socket_timeout
        return redis.ConnectionPool(
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            socket_timeout=timeout,
            decode_responses=self.config.decode_responses,
            max_connections=10,
        )

    def connect(self) -> redis.Redis | None:
        """Get or create Redis connection.

        Returns:
            Redis client or None if connection fails (graceful degradation)
        """
        with self._lock:
            if self._client is not None and self._connected:
                return self._client

            try:
                if self._pool is None:
                    self._pool = self._create_pool()

                self._client = redis.Redis(connection_pool=self._pool)
                # Test connection
                self._client.ping()
                self._connected = True
                logger.info(f"Connected to Redis at {self.config.host}:{self.config.port}")
                return self._client

            except (ConnectionError, TimeoutError, OSError) as e:
                self._connected = False
                logger.warning(
                    f"Redis connection failed: {e}. "
                    "Signals will not be published (graceful degradation)."
                )
                return None

    def disconnect(self) -> None:
        """Close Redis connection."""
        with self._lock:
            if self._pool is not None:
                self._pool.disconnect()
                self._pool = None
            self._client = None
            self._connected = False
            logger.info("Redis connection closed")

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        if not self._connected or self._client is None:
            return False
        try:
            self._client.ping()
            return True
        except (ConnectionError, TimeoutError):
            self._connected = False
            return False

    def publish(self, channel: str, message: str) -> int | None:
        """Publish message to Redis channel.

        Args:
            channel: Channel name
            message: Message to publish (JSON string)

        Returns:
            Number of subscribers that received the message, or None if not connected
        """
        client = self.connect()
        if client is None:
            logger.warning(f"Cannot publish to {channel}: Redis not connected")
            return None

        try:
            result = client.publish(channel, message)
            logger.debug(f"Published to {channel}: {result} subscribers")
            return result
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Failed to publish to {channel}: {e}")
            self._connected = False
            return None

    @contextmanager
    def pubsub(self, *, blocking: bool = False) -> Generator[redis.client.PubSub | None, None, None]:
        """Context manager for pub/sub operations.

        Yields:
            PubSub instance or None if not connected

        Usage:
            with client.pubsub() as ps:
                if ps:
                    ps.subscribe("channel")
                    for msg in ps.listen():
                        handle(msg)
        """
        pool: redis.ConnectionPool | None = None
        client: redis.Redis | None
        if blocking:
            try:
                pool = self._create_pool(socket_timeout=None)
                client = redis.Redis(connection_pool=pool)
                client.ping()
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning(
                    f"Redis blocking pubsub connection failed: {e}. "
                    "Signals will not be consumed until Redis is available."
                )
                if pool is not None:
                    pool.disconnect()
                yield None
                return
        else:
            client = self.connect()
            if client is None:
                yield None
                return

        ps = client.pubsub()
        try:
            yield ps
        finally:
            ps.close()
            if pool is not None:
                try:
                    client.close()
                except redis.RedisError:
                    pass
                pool.disconnect()

    def subscribe(self, channel: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Subscribe to channel with callback.

        Args:
            channel: Channel name to subscribe to
            callback: Function to call on each message

        Note:
            This is a blocking operation. Run in a separate thread.
        """
        client = self.connect()
        if client is None:
            logger.warning(f"Cannot subscribe to {channel}: Redis not connected")
            return

        ps = client.pubsub()
        ps.subscribe(channel)
        logger.info(f"Subscribed to {channel}")

        try:
            for message in ps.listen():
                if message["type"] == "message":
                    callback(message)
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Subscription to {channel} failed: {e}")
            self._connected = False
        finally:
            ps.close()

    def __enter__(self) -> "RedisClient":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


# Global client instance (lazy initialization)
_redis_client: RedisClient | None = None
_client_lock = Lock()


def get_redis_client() -> RedisClient:
    """Get global Redis client (singleton).

    Returns:
        RedisClient instance
    """
    global _redis_client
    with _client_lock:
        if _redis_client is None:
            _redis_client = RedisClient()
        return _redis_client


def close_redis_client() -> None:
    """Close global Redis client."""
    global _redis_client
    with _client_lock:
        if _redis_client is not None:
            _redis_client.disconnect()
            _redis_client = None
