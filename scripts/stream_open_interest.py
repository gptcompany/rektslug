#!/usr/bin/env python3
"""Real-time Open Interest streaming from Binance Futures REST API.

Binance does not provide a native WebSocket stream for Open Interest data.
This script polls the REST API endpoint at configurable intervals and
appends new data to the open_interest_history DuckDB table.

Usage:
    # Run as foreground process
    python scripts/stream_open_interest.py

    # Run as background service (systemd-friendly)
    python scripts/stream_open_interest.py --daemon

    # Custom polling interval (default: 60 seconds)
    python scripts/stream_open_interest.py --interval 30

Architecture:
    - Uses httpx for async HTTP requests with connection pooling
    - Exponential backoff retry logic for API failures
    - Thread-safe DuckDB writes with connection locking
    - Graceful shutdown on SIGTERM/SIGINT

References:
    - Binance API: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Optional

import duckdb
import httpx

# Configuration
DEFAULT_DB_PATH = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb"
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_POLL_INTERVAL = 60  # seconds (Binance updates OI every minute)
BINANCE_API_BASE = "https://fapi.binance.com"
OPEN_INTEREST_ENDPOINT = "/fapi/v1/openInterest"
TICKER_ENDPOINT = "/fapi/v1/ticker/price"

# Retry configuration
MAX_RETRIES = 5
BASE_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 60.0  # seconds

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("stream_open_interest")


class OpenInterestStreamer:
    """Streams Open Interest data from Binance to DuckDB."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        symbol: str = DEFAULT_SYMBOL,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ):
        """Initialize the streamer.

        Args:
            db_path: Path to DuckDB database file
            symbol: Trading pair symbol (e.g., BTCUSDT)
            poll_interval: Seconds between API polls
        """
        self.db_path = Path(db_path)
        self.symbol = symbol
        self.poll_interval = poll_interval

        self._running = False
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._conn_lock = Lock()
        self._client: Optional[httpx.AsyncClient] = None

        # Stats tracking
        self._successful_inserts = 0
        self._failed_requests = 0
        self._duplicates_skipped = 0
        self._start_time: Optional[datetime] = None

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get or create DuckDB connection (thread-safe)."""
        with self._conn_lock:
            if self._conn is None:
                if not self.db_path.exists():
                    raise FileNotFoundError(
                        f"Database not found: {self.db_path}. Run init_database.py first."
                    )
                self._conn = duckdb.connect(str(self.db_path))
                logger.info(f"Connected to DuckDB: {self.db_path}")
            return self._conn

    def _close_connection(self):
        """Close DuckDB connection."""
        with self._conn_lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                logger.info("DuckDB connection closed")

    async def _fetch_open_interest(self) -> Optional[dict]:
        """Fetch current Open Interest from Binance API.

        Returns:
            dict with openInterest, symbol, time or None on failure
        """
        url = f"{BINANCE_API_BASE}{OPEN_INTEREST_ENDPOINT}"
        params = {"symbol": self.symbol}

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                # Binance OI response format:
                # {"openInterest": "12345.678", "symbol": "BTCUSDT", "time": 1234567890000}
                return {
                    "open_interest_contracts": Decimal(data["openInterest"]),
                    "symbol": data["symbol"],
                    "timestamp_ms": data["time"],
                }

            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP error {e.response.status_code} on attempt {attempt + 1}: {e}")
            except httpx.RequestError as e:
                logger.warning(f"Request error on attempt {attempt + 1}: {e}")
            except (KeyError, ValueError) as e:
                logger.error(f"Invalid API response format: {e}")
                return None

            # Exponential backoff
            if attempt < MAX_RETRIES - 1:
                delay = min(BASE_RETRY_DELAY * (2**attempt), MAX_RETRY_DELAY)
                logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

        self._failed_requests += 1
        logger.error(f"Failed to fetch OI after {MAX_RETRIES} attempts")
        return None

    async def _fetch_current_price(self) -> Optional[Decimal]:
        """Fetch current price for OI value calculation.

        Returns:
            Current price as Decimal or None on failure
        """
        url = f"{BINANCE_API_BASE}{TICKER_ENDPOINT}"
        params = {"symbol": self.symbol}

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return Decimal(data["price"])
        except Exception as e:
            logger.warning(f"Failed to fetch price: {e}")
            return None

    def _insert_oi_record(
        self,
        timestamp: datetime,
        symbol: str,
        oi_contracts: Decimal,
        oi_value: Decimal,
    ) -> bool:
        """Insert OI record into DuckDB.

        Args:
            timestamp: Record timestamp
            symbol: Trading pair
            oi_contracts: Open Interest in contracts
            oi_value: Open Interest in USD value

        Returns:
            True if inserted, False if duplicate/error
        """
        conn = self._get_connection()

        try:
            # Get next ID
            max_id = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM open_interest_history"
            ).fetchone()[0]

            # Calculate OI delta from previous record
            prev_oi = conn.execute(
                """
                SELECT open_interest_value
                FROM open_interest_history
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                [symbol],
            ).fetchone()

            oi_delta = None
            if prev_oi and prev_oi[0]:
                oi_delta = oi_value - prev_oi[0]

            # Check for duplicate (same timestamp for this symbol)
            existing = conn.execute(
                """
                SELECT 1 FROM open_interest_history
                WHERE timestamp = ? AND symbol = ?
                LIMIT 1
                """,
                [timestamp, symbol],
            ).fetchone()

            if existing:
                self._duplicates_skipped += 1
                logger.debug(f"Duplicate record skipped: {timestamp}")
                return False

            # Insert new record
            conn.execute(
                """
                INSERT INTO open_interest_history
                (id, timestamp, symbol, open_interest_value,
                 open_interest_contracts, source, oi_delta)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    max_id + 1,
                    timestamp,
                    symbol,
                    float(oi_value),  # DuckDB DECIMAL from float
                    float(oi_contracts),
                    "binance_realtime",  # Different source marker
                    float(oi_delta) if oi_delta else None,
                ],
            )

            self._successful_inserts += 1
            logger.info(
                f"Inserted OI: {oi_contracts:,.2f} contracts, "
                f"${oi_value:,.0f} value, delta: {oi_delta:+,.0f}"
                if oi_delta
                else ""
            )
            return True

        except duckdb.ConstraintException as e:
            self._duplicates_skipped += 1
            logger.debug(f"Constraint violation (duplicate): {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to insert OI record: {e}")
            return False

    async def _poll_once(self):
        """Execute one poll cycle."""
        # Fetch OI and price in parallel
        oi_data, price = await asyncio.gather(
            self._fetch_open_interest(),
            self._fetch_current_price(),
        )

        if oi_data is None:
            logger.warning("Skipping insert due to OI fetch failure")
            return

        # Calculate OI value (contracts * current price)
        oi_contracts = oi_data["open_interest_contracts"]
        if price:
            oi_value = oi_contracts * price
        else:
            # Fallback: estimate from recent data
            logger.warning("Using estimated price from recent OI value")
            conn = self._get_connection()
            recent = conn.execute(
                """
                SELECT open_interest_value / NULLIF(open_interest_contracts, 0)
                FROM open_interest_history
                WHERE symbol = ? AND open_interest_contracts > 0
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                [self.symbol],
            ).fetchone()
            if recent and recent[0]:
                oi_value = oi_contracts * Decimal(str(recent[0]))
            else:
                logger.error("Cannot calculate OI value without price")
                return

        # Convert timestamp (Binance returns milliseconds)
        timestamp = datetime.fromtimestamp(oi_data["timestamp_ms"] / 1000, tz=timezone.utc)
        # Remove timezone for DuckDB TIMESTAMP compatibility
        timestamp = timestamp.replace(tzinfo=None)

        self._insert_oi_record(
            timestamp=timestamp,
            symbol=oi_data["symbol"],
            oi_contracts=oi_contracts,
            oi_value=oi_value,
        )

    def _log_stats(self):
        """Log current statistics."""
        if self._start_time:
            runtime = datetime.now() - self._start_time

            logger.info(
                f"Stats - Inserts: {self._successful_inserts}, "
                f"Duplicates: {self._duplicates_skipped}, "
                f"Failures: {self._failed_requests}, "
                f"Runtime: {runtime}"
            )

    async def run(self):
        """Main run loop."""
        self._running = True
        self._start_time = datetime.now()

        logger.info(f"Starting Open Interest streamer for {self.symbol}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"Database: {self.db_path}")

        # Verify database connection
        try:
            conn = self._get_connection()
            count = conn.execute(
                "SELECT COUNT(*) FROM open_interest_history WHERE symbol = ?",
                [self.symbol],
            ).fetchone()[0]
            logger.info(f"Existing OI records for {self.symbol}: {count:,}")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return

        # Create HTTP client with connection pooling
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=10),
        ) as client:
            self._client = client

            poll_count = 0
            while self._running:
                try:
                    await self._poll_once()
                    poll_count += 1

                    # Log stats every 10 polls
                    if poll_count % 10 == 0:
                        self._log_stats()

                    # Wait for next poll
                    await asyncio.sleep(self.poll_interval)

                except asyncio.CancelledError:
                    logger.info("Received cancellation request")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in poll loop: {e}")
                    await asyncio.sleep(self.poll_interval)

        self._log_stats()
        logger.info("Streamer stopped")

    def stop(self):
        """Signal the streamer to stop."""
        logger.info("Stop signal received")
        self._running = False

    def cleanup(self):
        """Clean up resources."""
        self._close_connection()


def setup_signal_handlers(streamer: OpenInterestStreamer, loop: asyncio.AbstractEventLoop):
    """Setup graceful shutdown handlers."""

    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        streamer.stop()
        # Schedule cleanup on the event loop
        loop.call_soon_threadsafe(streamer.cleanup)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)


def main():
    parser = argparse.ArgumentParser(
        description="Stream Open Interest from Binance to DuckDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage (polls every 60 seconds)
    python scripts/stream_open_interest.py

    # Faster polling (every 30 seconds)
    python scripts/stream_open_interest.py --interval 30

    # Different symbol
    python scripts/stream_open_interest.py --symbol ETHUSDT

    # Run as systemd service
    python scripts/stream_open_interest.py --daemon
        """,
    )
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help=f"Trading pair symbol (default: {DEFAULT_SYMBOL})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        help=f"Poll interval in seconds (default: {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"Database path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as background daemon (systemd-friendly)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # Validate interval
    if args.interval < 5:
        logger.warning("Interval < 5s may hit rate limits. Setting to 5s.")
        args.interval = 5

    # Create streamer
    streamer = OpenInterestStreamer(
        db_path=args.db,
        symbol=args.symbol,
        poll_interval=args.interval,
    )

    # Get event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Setup signal handlers
    setup_signal_handlers(streamer, loop)

    try:
        loop.run_until_complete(streamer.run())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        streamer.cleanup()
        loop.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
