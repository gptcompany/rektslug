"""Feedback Consumer for Adaptive Signal Loop.

Consumes P&L feedback from trading systems (Nautilus) via Redis pub/sub
and stores in DuckDB for rolling metric calculations.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import duckdb
from redis.exceptions import ConnectionError

from src.liquidationheatmap.signals.config import get_signal_channel
from src.liquidationheatmap.signals.models import TradeFeedback
from src.liquidationheatmap.signals.redis_client import RedisClient, get_redis_client

logger = logging.getLogger(__name__)
DEFAULT_FEEDBACK_DB_PATH = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb"
SIGNAL_FEEDBACK_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "migrations" / "add_signal_feedback_table.sql"
)


def resolve_feedback_db_path() -> str:
    """Resolve the DuckDB path for feedback persistence.

    Prefer the explicit feedback path if present, otherwise reuse the standard
    heatmap DB path already wired through the runtime.
    """
    return (
        os.getenv("FEEDBACK_DB_PATH")
        or os.getenv("HEATMAP_DB_PATH")
        or os.getenv("HEATMAP_CONTAINER_DB_PATH")
        or DEFAULT_FEEDBACK_DB_PATH
    )


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
        self._schema_ready = False

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """Get DuckDB connection (lazy initialization)."""
        if self._conn is None:
            db_path = resolve_feedback_db_path()
            self._conn = duckdb.connect(db_path, read_only=self._read_only)
        if not self._schema_ready:
            self.ensure_schema()
        return self._conn

    def ensure_schema(self) -> None:
        """Ensure the feedback table exists for write-capable connections."""
        if self._schema_ready:
            return
        if self._read_only:
            self._schema_ready = True
            return

        migration_sql = SIGNAL_FEEDBACK_MIGRATION_PATH.read_text()
        self._conn.execute(migration_sql)
        self._schema_ready = True

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

    def healthcheck(self) -> bool:
        """Validate DB connectivity and the feedback schema."""
        try:
            self.conn.execute("SELECT 1 FROM signal_feedback LIMIT 1")
            return True
        except Exception as e:
            logger.error(f"Feedback DB healthcheck failed: {e}")
            return False

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
        persisted_count: Number of successfully stored feedback records

    Usage:
        consumer = FeedbackConsumer()
        consumer.subscribe_feedback(["BTCUSDT", "ETHUSDT"])  # Blocking
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
        self.persisted_count = 0

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
            success = self.store_feedback(feedback)
            if success:
                self.persisted_count += 1
            return success
        except Exception as e:
            logger.error(f"Failed to store feedback: {e}")
            return False

    def subscribe_feedback(
        self,
        symbol: str | list[str],
        callback: Any | None = None,
        timeout: float | None = None,
    ) -> None:
        """Subscribe to feedback channel for one or more symbols.

        Args:
            symbol: Trading pair symbol or list of symbols
            callback: Optional callback for each message (default: store in DB)
            timeout: Optional timeout in seconds (None = run forever)

        Note:
            This is a blocking operation. Run in a separate thread for async.
        """
        if isinstance(symbol, str):
            channels = [get_signal_channel(symbol, "feedback")]
        else:
            channels = [get_signal_channel(s, "feedback") for s in symbol]

        start_time = time.time()

        while True:
            try:
                with self.redis_client.pubsub() as ps:
                    if ps is None:
                        logger.warning("Redis not available for feedback subscription")
                        time.sleep(5)
                        continue

                    ps.subscribe(*channels)
                    logger.info(f"Subscribed to feedback channels: {channels}")

                    for message in ps.listen():
                        # Check timeout
                        if timeout is not None:
                            if time.time() - start_time > timeout:
                                logger.debug("Subscription timeout reached")
                                return

                        if message["type"] == "subscribe":
                            continue

                        if message["type"] == "message":
                            if callback:
                                callback(message)
                            else:
                                self.process_message(message)
            except ConnectionError as e:
                logger.error(f"Redis connection error: {e}. Reconnecting in 5 seconds...")
                time.sleep(5)
            except KeyboardInterrupt:
                logger.info("Feedback subscription interrupted")
                break
            except Exception as e:
                logger.error(f"Unexpected error in feedback subscription: {e}")
                time.sleep(5)

            if timeout is not None and time.time() - start_time > timeout:
                break

    def close(self) -> None:
        """Close Redis and database connections."""
        if self._redis_client is not None:
            self._redis_client.disconnect()
        if self._db_service is not None and hasattr(self._db_service, "close"):
            self._db_service.close()


def run_healthcheck() -> bool:
    """Validate the feedback service dependencies without taking write locks."""
    redis_client = get_redis_client()
    db_service = FeedbackDBService(read_only=True)
    try:
        redis_ok = redis_client.is_connected
        if not redis_ok:
            logger.error("Feedback Redis healthcheck failed: Redis not connected")

        db_ok = db_service.healthcheck()
        return redis_ok and db_ok
    finally:
        db_service.close()
        redis_client.disconnect()


def main():
    """CLI entry point for feedback consumer."""
    parser = argparse.ArgumentParser(description="Consume P&L feedback from Redis")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair symbol")
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="List of symbols to subscribe to (overrides --symbol)",
    )
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Validate feedback DB connectivity/schema and exit",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    consumer = FeedbackConsumer()
    if args.healthcheck:
        sys.exit(0 if run_healthcheck() else 1)

    symbols = args.symbols if args.symbols else args.symbol
    logger.info(f"Starting feedback consumer for {symbols}")
    try:
        if hasattr(consumer.db_service, "ensure_schema"):
            consumer.db_service.ensure_schema()
        consumer.subscribe_feedback(symbols)
    except KeyboardInterrupt:
        logger.info("Shutting down feedback consumer")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
