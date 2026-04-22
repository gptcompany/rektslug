"""Feedback Consumer for Adaptive Signal Loop.

Consumes P&L feedback from trading systems (Nautilus) via Redis pub/sub
and stores in DuckDB for rolling metric calculations.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
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
DEFAULT_CONTINUOUS_RUNTIME_REPORT_NAME = "continuous_runtime_report.json"
CONTINUOUS_REPORT_RUNTIME_FIELDS = (
    "session_started_at",
    "timestamp",
    "runtime_seconds",
    "signals_seen",
    "signals_rejected",
    "signals_accepted",
    "orders_submitted",
    "orders_rejected",
    "orders_filled",
    "positions_opened",
    "positions_closed",
    "feedback_published",
    "residual_open_positions",
    "residual_open_orders",
)


class ContinuousReportUnavailableError(RuntimeError):
    """Raised when the continuous runtime report cannot be produced safely."""


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


def resolve_continuous_runtime_report_path() -> Path:
    """Resolve the runtime snapshot used to build the continuous report."""
    configured = (
        os.getenv("HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH")
        or os.getenv("CONTINUOUS_RUNTIME_REPORT_PATH")
    )
    if configured:
        return Path(configured)
    return Path(resolve_feedback_db_path()).resolve().parent / DEFAULT_CONTINUOUS_RUNTIME_REPORT_NAME


def _parse_iso8601(value: str, field_name: str) -> datetime:
    """Parse an ISO8601 timestamp into a UTC-aware datetime."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuousReportUnavailableError(
            f"continuous runtime report has invalid {field_name}: {value}"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_continuous_runtime_snapshot() -> dict[str, Any]:
    """Load and validate the continuous runtime snapshot from disk."""
    report_path = resolve_continuous_runtime_report_path()
    if not report_path.exists():
        raise ContinuousReportUnavailableError(
            f"continuous runtime report missing: {report_path}"
        )

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContinuousReportUnavailableError(
            f"continuous runtime report unreadable: {report_path}"
        ) from exc

    missing_fields = [
        field_name
        for field_name in CONTINUOUS_REPORT_RUNTIME_FIELDS
        if payload.get(field_name) is None
    ]
    if missing_fields:
        raise ContinuousReportUnavailableError(
            "continuous runtime report missing required fields: "
            + ", ".join(sorted(missing_fields))
        )

    return payload


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

        if self._conn is None:
            db_path = resolve_feedback_db_path()
            self._conn = duckdb.connect(db_path, read_only=False)

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

    def get_continuous_report(self, runtime_snapshot: dict[str, Any]) -> Any:
        """Get machine-readable continuous report with measured runtime counters.

        Returns:
            ContinuousReport containing non-null lifecycle counters.
        """
        from src.liquidationheatmap.signals.models import ContinuousReport

        session_started_at = _parse_iso8601(
            str(runtime_snapshot["session_started_at"]),
            "session_started_at",
        )
        report_timestamp = _parse_iso8601(
            str(runtime_snapshot["timestamp"]),
            "timestamp",
        )

        try:
            result = self.conn.execute(
                """
                SELECT COUNT(*)
                FROM signal_feedback
                WHERE created_at >= ?
                """,
                [session_started_at.replace(tzinfo=None)],
            ).fetchone()
            feedback_persisted = result[0] if result else 0
        except Exception as e:
            logger.warning(f"Could not count persisted feedback: {e}")
            raise ContinuousReportUnavailableError(
                "continuous runtime report unavailable: could not count persisted feedback"
            ) from e

        feedback_published = int(runtime_snapshot["feedback_published"])
        blocking_issues: list[str] = []
        if feedback_published != feedback_persisted:
            blocking_issues.append(
                "feedback_publish_persist_mismatch:"
                f" published={feedback_published} persisted={feedback_persisted}"
            )

        return ContinuousReport(
            session_started_at=session_started_at,
            timestamp=report_timestamp,
            runtime_seconds=float(runtime_snapshot["runtime_seconds"]),
            signals_seen=int(runtime_snapshot["signals_seen"]),
            signals_rejected=int(runtime_snapshot["signals_rejected"]),
            signals_accepted=int(runtime_snapshot["signals_accepted"]),
            orders_submitted=int(runtime_snapshot["orders_submitted"]),
            orders_rejected=int(runtime_snapshot["orders_rejected"]),
            orders_filled=int(runtime_snapshot["orders_filled"]),
            positions_opened=int(runtime_snapshot["positions_opened"]),
            positions_closed=int(runtime_snapshot["positions_closed"]),
            feedback_published=feedback_published,
            feedback_persisted=feedback_persisted,
            persistence_consistent=feedback_published == feedback_persisted,
            report_status="blocked" if blocking_issues else "ok",
            blocking_issues=blocking_issues,
            residual_open_positions=int(runtime_snapshot["residual_open_positions"]),
            residual_open_orders=int(runtime_snapshot["residual_open_orders"]),
        )

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
                with self.redis_client.pubsub(blocking=True) as ps:
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
    """Validate feedback service reachability without contending on the writer lock."""
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    db_path = Path(resolve_feedback_db_path())

    try:
        with socket.create_connection((redis_host, redis_port), timeout=1.0):
            redis_ok = True
    except OSError as exc:
        logger.error(f"Feedback Redis healthcheck failed: {exc}")
        redis_ok = False

    db_ok = db_path.exists()
    if not db_ok:
        logger.error(f"Feedback DB healthcheck failed: missing file {db_path}")

    return redis_ok and db_ok


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
