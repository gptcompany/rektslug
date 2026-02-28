"""Feedback Consumer for Adaptive Signal Loop.

Consumes P&L feedback from trading systems (Nautilus) via Redis pub/sub
and stores in DuckDB for rolling metric calculations.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import duckdb

from src.liquidationheatmap.signals.config import get_signal_channel
from src.liquidationheatmap.signals.models import TradeFeedback
from src.liquidationheatmap.signals.redis_client import RedisClient, get_redis_client

logger = logging.getLogger(__name__)


class DBServiceProtocol(Protocol):
    """Protocol for database service."""

    def store_feedback(self, feedback: TradeFeedback) -> bool: ...


class FeedbackDBService:
    """DuckDB service for storing and querying feedback.

    Provides persistence layer for TradeFeedback records.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection | None = None,
        read_only: bool = False,
    ):
        """Initialize FeedbackDBService.

        Args:
            conn: DuckDB connection (creates in-memory if None)
            read_only: If True, open database in read-only mode (no write lock)
        """
        self._conn = conn
        self._read_only = read_only

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """Get DuckDB connection (lazy initialization)."""
        if self._conn is None:
            # Use default path or create in-memory for tests
            import os

            db_path = os.getenv("FEEDBACK_DB_PATH", "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb")
            self._conn = duckdb.connect(db_path, read_only=self._read_only)
        return self._conn

    def store_feedback(self, feedback: TradeFeedback) -> bool:
        """Store feedback record in DuckDB.

        Args:
            feedback: TradeFeedback object to store

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            self.conn.execute(
                """
                INSERT INTO signal_feedback
                (symbol, signal_id, entry_price, exit_price, pnl, timestamp, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    feedback.symbol,
                    feedback.signal_id,
                    float(feedback.entry_price),
                    float(feedback.exit_price),
                    float(feedback.pnl),
                    feedback.timestamp,
                    feedback.source,
                ],
            )
            logger.debug(f"Stored feedback: signal_id={feedback.signal_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store feedback: {e}")
            return False

    def get_rolling_metrics(self, symbol: str, hours: int = 24) -> dict[str, Any]:
        """Calculate rolling metrics for a symbol.

        Args:
            symbol: Trading pair symbol
            hours: Rolling window in hours

        Returns:
            Dict with metrics: total, profitable, unprofitable, hit_rate, avg_pnl
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        try:
            result = self.conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN pnl > 0 THEN 1 END) as profitable,
                    AVG(pnl) as avg_pnl
                FROM signal_feedback
                WHERE symbol = ? AND timestamp >= ?
                """,
                [symbol, cutoff],
            ).fetchone()

            total = result[0] or 0
            profitable = result[1] or 0
            avg_pnl = result[2] or 0.0

            return {
                "total": total,
                "profitable": profitable,
                "unprofitable": total - profitable,
                "hit_rate": profitable / total if total > 0 else 0.0,
                "avg_pnl": avg_pnl,
            }
        except Exception as e:
            # Table may not exist yet - return empty metrics
            logger.warning(f"Could not fetch rolling metrics for {symbol}: {e}")
            return {
                "total": 0,
                "profitable": 0,
                "unprofitable": 0,
                "hit_rate": 0.0,
                "avg_pnl": 0.0,
            }

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class FeedbackConsumer:
    """Consumes P&L feedback from Redis and stores in DuckDB.

    Attributes:
        redis_client: Redis client for pub/sub
        db_service: Database service for storage

    Usage:
        consumer = FeedbackConsumer()
        consumer.subscribe_feedback("BTCUSDT")  # Blocking
    """

    def __init__(
        self,
        redis_client: RedisClient | None = None,
        db_service: DBServiceProtocol | None = None,
    ):
        """Initialize FeedbackConsumer.

        Args:
            redis_client: Redis client (uses global client if None)
            db_service: Database service (creates FeedbackDBService if None)
        """
        self._redis_client = redis_client
        self._db_service = db_service

    @property
    def redis_client(self) -> RedisClient:
        """Get Redis client (lazy initialization)."""
        if self._redis_client is None:
            self._redis_client = get_redis_client()
        return self._redis_client

    @property
    def db_service(self) -> DBServiceProtocol:
        """Get database service (lazy initialization)."""
        if self._db_service is None:
            self._db_service = FeedbackDBService()
        return self._db_service

    def store_feedback(self, feedback: TradeFeedback) -> bool:
        """Store feedback in DuckDB.

        Args:
            feedback: TradeFeedback object

        Returns:
            True if stored successfully
        """
        return self.db_service.store_feedback(feedback)

    def process_message(self, message: dict[str, Any]) -> bool:
        """Process a Redis pub/sub message.

        Args:
            message: Redis message dict with 'type', 'channel', 'data'

        Returns:
            True if processed successfully, False if parsing/storage failed
        """
        if message.get("type") != "message":
            return False

        data = message.get("data", "")

        try:
            feedback = TradeFeedback.from_redis_message(data)
        except Exception as e:
            logger.warning(f"Failed to parse feedback message: {e}")
            return False

        try:
            return self.store_feedback(feedback)
        except Exception as e:
            logger.error(f"Failed to store feedback: {e}")
            return False

    def subscribe_feedback(
        self,
        symbol: str,
        callback: Any | None = None,
        timeout: float | None = None,
    ) -> None:
        """Subscribe to feedback channel for a symbol.

        Args:
            symbol: Trading pair symbol
            callback: Optional callback for each message (default: store in DB)
            timeout: Optional timeout in seconds (None = run forever)

        Note:
            This is a blocking operation. Run in a separate thread for async.
        """
        channel = get_signal_channel(symbol, "feedback")

        with self.redis_client.pubsub() as ps:
            if ps is None:
                logger.warning("Redis not available for feedback subscription")
                return

            ps.subscribe(channel)
            logger.info(f"Subscribed to feedback channel: {channel}")

            import time

            start_time = time.time()

            try:
                for message in ps.listen():
                    # Check timeout
                    if timeout is not None:
                        if time.time() - start_time > timeout:
                            logger.debug("Subscription timeout reached")
                            break

                    if message["type"] == "subscribe":
                        continue

                    if message["type"] == "message":
                        if callback:
                            callback(message)
                        else:
                            self.process_message(message)
            except KeyboardInterrupt:
                logger.info("Feedback subscription interrupted")

    def close(self) -> None:
        """Close Redis and database connections."""
        if self._redis_client is not None:
            self._redis_client.disconnect()
        if self._db_service is not None and hasattr(self._db_service, "close"):
            self._db_service.close()


def main():
    """CLI entry point for feedback consumer."""
    parser = argparse.ArgumentParser(description="Consume P&L feedback from Redis")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair symbol")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    logger.info(f"Starting feedback consumer for {args.symbol}")

    consumer = FeedbackConsumer()
    try:
        consumer.subscribe_feedback(args.symbol)
    except KeyboardInterrupt:
        logger.info("Shutting down feedback consumer")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
