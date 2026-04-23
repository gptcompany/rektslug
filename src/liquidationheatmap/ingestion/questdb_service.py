"""QuestDB service for high-frequency time-series data storage and retrieval."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg2

try:
    from questdb.ingress import Sender, TimestampNanos
except ModuleNotFoundError:  # pragma: no cover - exercised in environments without questdb client
    Sender = None

    class TimestampNanos:
        @staticmethod
        def now() -> int:
            return time.time_ns()

from src.liquidationheatmap.api.metrics import (
    QUESTDB_AVAILABLE,
    QUESTDB_INGEST_TOTAL,
    QUESTDB_QUERY_DURATION,
    QUESTDB_QUERY_TOTAL,
)

from ..settings import get_settings

logger = logging.getLogger(__name__)


class QuestDBService:
    """Service for managing QuestDB connection (ILP and SQL)."""

    _instance: Optional["QuestDBService"] = None
    _lock = __import__("threading").Lock()

    def __new__(cls):
        """Singleton pattern for QuestDB service."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize QuestDB service only once per singleton."""
        if self._initialized:
            return

        settings = get_settings()
        self.host = settings.questdb_host
        self.port = settings.questdb_port
        self.pg_port = settings.questdb_pg_port

        self._sender_conf: str | None = None

        if Sender is None:
            logger.warning("QuestDB Python client not installed; ILP ingestion disabled")
            self._sender = None
        else:
            try:
                self._sender_conf = f"tcp::addr={self.host}:{self.port};"
                probe = Sender.from_conf(self._sender_conf)
                probe.close()
                self._sender = self._sender_conf
                logger.info("QuestDB ILP sender configured for %s:%s", self.host, self.port)
            except Exception as exc:
                logger.error("Failed to initialize QuestDB ILP Sender: %s", exc)
                self._sender = None
                self._sender_conf = None

        self._initialized = True

    @staticmethod
    def _query_kind(query: str) -> str:
        stripped = query.strip()
        if not stripped:
            return "unknown"
        return stripped.split(None, 1)[0].lower()

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @classmethod
    def reset_singleton(cls) -> None:
        with cls._lock:
            cls._instance = None

    def _observe_query(self, query: str, status: str, started_at: float) -> None:
        query_kind = self._query_kind(query)
        QUESTDB_QUERY_TOTAL.labels(query_kind=query_kind, status=status).inc()
        QUESTDB_QUERY_DURATION.labels(query_kind=query_kind, status=status).observe(
            max(0.0, time.perf_counter() - started_at)
        )

    def _record_ingest(self, table: str, status: str) -> None:
        QUESTDB_INGEST_TOTAL.labels(table=table, status=status).inc()

    def _open_sender(self):
        if not self._sender_conf or Sender is None:
            return None
        return Sender.from_conf(self._sender_conf)

    def _get_pg_conn(self):
        """Get a Postgres wire protocol connection for SQL queries."""
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.pg_port,
                user="admin",
                password="quest",
                database="qdb",
                connect_timeout=5,
            )
            QUESTDB_AVAILABLE.set(1)
            return conn
        except Exception as exc:
            QUESTDB_AVAILABLE.set(0)
            logger.error("Failed to connect to QuestDB via Postgres wire: %s", exc)
            return None

    def execute_query(self, query: str, params: Optional[list[Any]] = None) -> list[tuple[Any, ...]]:
        """Execute a SQL query against QuestDB."""
        started_at = time.perf_counter()
        conn = self._get_pg_conn()
        if not conn:
            self._observe_query(query, "unavailable", started_at)
            return []

        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if cur.description is None:
                    conn.commit()
                    self._observe_query(query, "success", started_at)
                    return []
                rows = cur.fetchall()
                self._observe_query(query, "success", started_at)
                return rows
        except Exception as exc:
            self._observe_query(query, "error", started_at)
            logger.error("QuestDB SQL query failed: %s", exc)
            return []
        finally:
            conn.close()

    def is_available(self) -> bool:
        """Return whether QuestDB SQL is reachable."""
        rows = self.execute_query("SELECT 1")
        return bool(rows and rows[0][0] == 1)

    def init_schema(self) -> None:
        """Initialize QuestDB schema for high-frequency tables."""
        self.execute_query(
            """
            CREATE TABLE IF NOT EXISTS open_interest (
                timestamp TIMESTAMP,
                symbol SYMBOL,
                open_interest_value DOUBLE
            ) timestamp(timestamp) PARTITION BY DAY WAL;
            """
        )
        self.execute_query(
            """
            CREATE TABLE IF NOT EXISTS funding_rates (
                timestamp TIMESTAMP,
                symbol SYMBOL,
                funding_rate DOUBLE
            ) timestamp(timestamp) PARTITION BY DAY WAL;
            """
        )
        self.execute_query(
            """
            CREATE TABLE IF NOT EXISTS liquidations (
                timestamp TIMESTAMP,
                symbol SYMBOL,
                side SYMBOL,
                price DOUBLE,
                quantity DOUBLE,
                leverage DOUBLE
            ) timestamp(timestamp) PARTITION BY DAY WAL;
            """
        )
        self.execute_query(
            """
            CREATE TABLE IF NOT EXISTS klines (
                timestamp TIMESTAMP,
                symbol SYMBOL,
                interval SYMBOL,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE
            ) timestamp(timestamp) PARTITION BY DAY WAL;
            """
        )
        logger.info("QuestDB schema initialization check complete")

    def ingest_oi(self, symbol: str, value: float, timestamp: Optional[int] = None) -> None:
        """Ingest Open Interest data via ILP."""
        if not self._sender:
            self._record_ingest("open_interest", "unavailable")
            return

        try:
            with self._open_sender() as sender:
                sender.row(
                    "open_interest",
                    symbols={"symbol": symbol},
                    columns={"open_interest_value": float(value)},
                    at=TimestampNanos.now() if timestamp is None else timestamp,
                )
                sender.flush()
            self._record_ingest("open_interest", "success")
        except Exception as exc:
            self._record_ingest("open_interest", "error")
            logger.error("QuestDB OI ingestion failed for %s: %s", symbol, exc)

    def ingest_funding(self, symbol: str, rate: float, timestamp: Optional[int] = None) -> None:
        """Ingest funding rate data via ILP."""
        if not self._sender:
            self._record_ingest("funding_rates", "unavailable")
            return

        try:
            with self._open_sender() as sender:
                sender.row(
                    "funding_rates",
                    symbols={"symbol": symbol},
                    columns={"funding_rate": float(rate)},
                    at=TimestampNanos.now() if timestamp is None else timestamp,
                )
                sender.flush()
            self._record_ingest("funding_rates", "success")
        except Exception as exc:
            self._record_ingest("funding_rates", "error")
            logger.error("QuestDB funding ingestion failed for %s: %s", symbol, exc)

    def ingest_liquidation(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        leverage: float,
        timestamp: Optional[int] = None,
    ) -> None:
        """Ingest a liquidation event via ILP."""
        if not self._sender:
            self._record_ingest("liquidations", "unavailable")
            return

        try:
            with self._open_sender() as sender:
                sender.row(
                    "liquidations",
                    symbols={"symbol": symbol, "side": side},
                    columns={
                        "price": float(price),
                        "quantity": float(quantity),
                        "leverage": float(leverage),
                    },
                    at=TimestampNanos.now() if timestamp is None else timestamp,
                )
                sender.flush()
            self._record_ingest("liquidations", "success")
        except Exception as exc:
            self._record_ingest("liquidations", "error")
            logger.error("QuestDB liquidation ingestion failed for %s: %s", symbol, exc)

    def get_latest_price(self, symbol: str, interval: Optional[str] = None) -> Optional[float]:
        """Get the latest close price from QuestDB klines."""
        query = """
            SELECT close
            FROM klines
            WHERE symbol = %s
        """
        params: list[Any] = [symbol]
        if interval is not None:
            query += " AND interval = %s"
            params.append(interval)
        query += " ORDER BY timestamp DESC LIMIT 1"
        results = self.execute_query(query, params)
        if results:
            return float(results[0][0])
        return None

    def get_latest_open_interest(self, symbol: str) -> tuple[Optional[float], Optional[float]]:
        """Get latest open interest and best-effort latest price."""
        results = self.execute_query(
            """
            SELECT open_interest_value
            FROM open_interest
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol],
        )
        if not results:
            return None, None

        oi_value = float(results[0][0])
        return self.get_latest_price(symbol), oi_value

    def get_latest_funding_rate(self, symbol: str) -> Optional[float]:
        """Get latest funding rate for a symbol."""
        results = self.execute_query(
            """
            SELECT funding_rate
            FROM funding_rates
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol],
        )
        if results:
            return float(results[0][0])
        return None

    def get_recent_klines(self, symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
        """Fetch recent klines from QuestDB."""
        rows = self.execute_query(
            """
            SELECT timestamp, symbol, interval, open, high, low, close, volume
            FROM klines
            WHERE symbol = %s AND interval = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            [symbol, interval, limit],
        )
        return [
            {
                "open_time": self._serialize_value(row[0]),
                "symbol": row[1],
                "interval": row[2],
                "open": row[3],
                "high": row[4],
                "low": row[5],
                "close": row[6],
                "volume": row[7],
            }
            for row in rows
        ]

    def get_klines_range(
        self,
        symbol: str,
        interval: str,
        start_time: Any,
        end_time: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch an ascending window of klines for internal heatmap computation."""
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM klines
            WHERE symbol = %s AND interval = %s AND timestamp >= %s
        """
        params: list[Any] = [symbol, interval, start_time]
        if end_time is not None:
            query += " AND timestamp <= %s"
            params.append(end_time)
        query += " ORDER BY timestamp ASC"
        rows = self.execute_query(query, params)
        return [
            {
                "timestamp": row[0],
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
            }
            for row in rows
        ]

    def get_open_interest_range(
        self,
        symbol: str,
        start_time: Any,
        end_time: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch an ascending window of open-interest samples with deltas."""
        query = """
            SELECT
                timestamp,
                open_interest_value,
                open_interest_value - LAG(open_interest_value) OVER (ORDER BY timestamp) AS oi_delta
            FROM open_interest
            WHERE symbol = %s AND timestamp >= %s
        """
        params: list[Any] = [symbol, start_time]
        if end_time is not None:
            query += " AND timestamp <= %s"
            params.append(end_time)
        query += " ORDER BY timestamp ASC"
        rows = self.execute_query(query, params)
        return [
            {
                "timestamp": row[0],
                "open_interest_value": row[1],
                "oi_delta": row[2],
            }
            for row in rows
        ]

    def get_open_interest_date_range(self, symbol: str) -> tuple[datetime, datetime] | None:
        """Fetch the min/max QuestDB timestamp for a symbol's OI data."""
        rows = self.execute_query(
            """
            SELECT MIN(timestamp), MAX(timestamp)
            FROM open_interest
            WHERE symbol = %s
            """,
            [symbol],
        )
        if not rows:
            return None
        start_date, end_date = rows[0]
        if start_date is None or end_date is None:
            return None
        return start_date, end_date

    def get_recent_liquidations(self, symbol: str, limit: int) -> list[dict[str, Any]]:
        """Fetch recent liquidation events from QuestDB."""
        rows = self.execute_query(
            """
            SELECT timestamp, symbol, side, price, quantity, leverage
            FROM liquidations
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            [symbol, limit],
        )
        return [
            {
                "timestamp": self._serialize_value(row[0]),
                "symbol": row[1],
                "side": row[2],
                "price": row[3],
                "quantity": row[4],
                "leverage": row[5],
            }
            for row in rows
        ]

    def ingest_dataframe(
        self,
        table_name: str,
        df,
        symbol_cols: Optional[list[str]] = None,
        timestamp_col: str = "timestamp",
    ) -> None:
        """Bulk ingest a Pandas DataFrame into QuestDB via ILP."""
        if not self._sender:
            self._record_ingest(table_name, "unavailable")
            raise RuntimeError(f"QuestDB sender unavailable for {table_name}")
        if df.empty:
            return

        symbol_cols = symbol_cols or []

        try:
            with self._open_sender() as sender:
                try:
                    sender.dataframe(
                        df,
                        table_name=table_name,
                        symbols=symbol_cols,
                        at=timestamp_col,
                    )
                except Exception as exc:
                    logger.warning(
                        "QuestDB dataframe ingest unavailable for %s, falling back to row mode: %s",
                        table_name,
                        exc,
                    )
                    for row in df.itertuples(index=False):
                        row_dict = row._asdict()
                        raw_ts = row_dict.pop(timestamp_col)
                        if hasattr(raw_ts, "to_pydatetime"):
                            raw_ts = raw_ts.to_pydatetime()
                        if isinstance(raw_ts, datetime):
                            if raw_ts.tzinfo is None:
                                raw_ts = raw_ts.replace(tzinfo=timezone.utc)
                        else:
                            at = datetime.fromtimestamp(int(raw_ts) / 1_000_000_000, tz=timezone.utc)
                        symbols = {col: row_dict.pop(col) for col in symbol_cols if col in row_dict}
                        sender.row(
                            table_name,
                            symbols=symbols,
                            columns=row_dict,
                            at=raw_ts if isinstance(raw_ts, datetime) else at,
                        )
                sender.flush()
            self._record_ingest(table_name, "success")
            logger.info("Ingested %s rows into QuestDB table %s", len(df), table_name)
        except Exception as exc:
            self._record_ingest(table_name, "error")
            logger.error("QuestDB bulk ingestion failed for %s: %s", table_name, exc)
            raise
