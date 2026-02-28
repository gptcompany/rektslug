#!/usr/bin/env python3
"""
Pre-computation script for time-evolving liquidation heatmap snapshots.

T055-T057 [US5] Pre-computation pipeline implementation:
- T055: Create pre-computation script
- T056: Add CLI arguments for symbol, date range, and interval
- T057: Implement batch snapshot generation and DuckDB persistence

Usage:
    # Pre-compute last 7 days of BTCUSDT data
    uv run python scripts/precompute_heatmap.py --symbol BTCUSDT --days 7

    # Pre-compute specific date range
    uv run python scripts/precompute_heatmap.py --symbol BTCUSDT \
        --start 2025-11-01 --end 2025-11-15

    # Pre-compute with custom interval
    uv run python scripts/precompute_heatmap.py --symbol BTCUSDT --days 30 --interval 15m
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import duckdb  # noqa: F401
except ImportError:
    print("Error: duckdb not installed. Run: uv add duckdb")
    sys.exit(1)

from src.liquidationheatmap.models.time_evolving_heatmap import (  # noqa: E402
    calculate_time_evolving_heatmap,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Pre-compute time-evolving liquidation heatmap snapshots",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Pre-compute last 7 days
    %(prog)s --symbol BTCUSDT --days 7

    # Pre-compute specific date range
    %(prog)s --symbol BTCUSDT --start 2025-11-01 --end 2025-11-15

    # Pre-compute with 1-hour interval
    %(prog)s --symbol BTCUSDT --days 30 --interval 1h
        """,
    )

    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading pair symbol (default: BTCUSDT)",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to pre-compute from today (default: 7)",
    )

    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD format). Overrides --days if provided",
    )

    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD format). Defaults to today",
    )

    parser.add_argument(
        "--interval",
        type=str,
        default="15m",
        choices=["5m", "15m", "30m", "1h", "4h"],
        help="Snapshot interval (default: 15m)",
    )

    parser.add_argument(
        "--price-bin-size",
        type=float,
        default=100.0,
        help="Price bin size in USDT (default: 100)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of snapshots per batch for persistence (default: 100)",
    )

    parser.add_argument(
        "--db-path",
        type=str,
        default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        help="Path to DuckDB database (default: /media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate but don't persist to database",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    return parser.parse_args()


def parse_date(date_str: str) -> datetime:
    """Parse date string to datetime."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")


def interval_to_minutes(interval: str) -> int:
    """Convert interval string to minutes."""
    mapping = {
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
    }
    return mapping.get(interval, 15)


def precompute_heatmap(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    interval: str,
    price_bin_size: float,
    db_path: str,
    batch_size: int,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """
    Pre-compute heatmap snapshots and persist to database.

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        start_time: Start of computation range
        end_time: End of computation range
        interval: Snapshot interval (5m, 15m, 30m, 1h, 4h)
        price_bin_size: Price bin size in USDT
        db_path: Path to DuckDB database
        batch_size: Snapshots per persistence batch
        dry_run: If True, don't persist to database
        verbose: Enable verbose logging

    Returns:
        Statistics dict with computation results
    """
    stats = {
        "snapshots_generated": 0,
        "snapshots_persisted": 0,
        "total_time_ms": 0,
        "errors": [],
    }

    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f"Starting pre-computation for {symbol}")
    logger.info(f"  Time range: {start_time} to {end_time}")
    logger.info(f"  Interval: {interval}")
    logger.info(f"  Price bin size: {price_bin_size}")
    logger.info(f"  Database: {db_path}")
    logger.info(f"  Dry run: {dry_run}")

    # Calculate total expected snapshots
    interval_minutes = interval_to_minutes(interval)
    total_minutes = (end_time - start_time).total_seconds() / 60
    expected_snapshots = int(total_minutes / interval_minutes)
    logger.info(f"  Expected snapshots: ~{expected_snapshots}")

    computation_start = time.perf_counter()

    try:
        # Import DuckDBService here to avoid module-level import issues
        from dataclasses import dataclass

        from src.liquidationheatmap.ingestion.db_service import DuckDBService

        @dataclass
        class Candle:
            """Candle data for heatmap calculation."""

            open_time: datetime
            open: Decimal
            high: Decimal
            low: Decimal
            close: Decimal
            volume: Decimal

        # Get database service
        db_service = DuckDBService(db_path)

        # Determine kline table based on interval
        interval_table_map = {
            "5m": "klines_5m_history",
            "15m": "klines_15m_history",
            "30m": "klines_5m_history",  # Aggregate from 5m
            "1h": "klines_5m_history",
            "4h": "klines_5m_history",
        }
        kline_table = interval_table_map.get(interval, "klines_15m_history")

        # Query candles from database
        logger.info(f"Fetching candles from {kline_table}...")
        candle_query = f"""
        SELECT
            open_time,
            CAST(open AS DECIMAL(18,8)) as open,
            CAST(high AS DECIMAL(18,8)) as high,
            CAST(low AS DECIMAL(18,8)) as low,
            CAST(close AS DECIMAL(18,8)) as close,
            CAST(volume AS DECIMAL(18,8)) as volume
        FROM {kline_table}
        WHERE symbol = ? AND open_time >= ? AND open_time <= ?
        ORDER BY open_time
        """
        candles_df = db_service.conn.execute(candle_query, [symbol, start_time, end_time]).df()

        if candles_df.empty:
            logger.warning(f"No candle data found for {symbol} in range {start_time} to {end_time}")
            stats["snapshots_generated"] = 0
            return stats

        logger.info(f"Loaded {len(candles_df)} candles")

        # Query OI data with delta calculation
        logger.info("Fetching OI deltas...")
        oi_query = """
        SELECT
            timestamp,
            open_interest_value,
            open_interest_value - LAG(open_interest_value) OVER (ORDER BY timestamp) as oi_delta
        FROM open_interest_history
        WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp
        """
        oi_df = db_service.conn.execute(oi_query, [symbol, start_time, end_time]).df()
        logger.info(f"Loaded {len(oi_df)} OI data points")

        # Convert to candle objects
        candles = [
            Candle(
                open_time=row["open_time"].to_pydatetime()
                if hasattr(row["open_time"], "to_pydatetime")
                else row["open_time"],
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
            )
            for _, row in candles_df.iterrows()
        ]

        # Match OI deltas to candles (approximate by nearest timestamp)
        oi_deltas = []
        oi_timestamps = oi_df["timestamp"].tolist() if not oi_df.empty else []
        oi_values = oi_df["oi_delta"].fillna(0).tolist() if not oi_df.empty else []

        for candle in candles:
            delta = Decimal("0")
            min_diff = float("inf")
            if oi_timestamps:
                for i, oi_ts in enumerate(oi_timestamps):
                    oi_ts_dt = oi_ts.to_pydatetime() if hasattr(oi_ts, "to_pydatetime") else oi_ts
                    diff = abs((candle.open_time - oi_ts_dt).total_seconds())
                    if diff < 900 and diff < min_diff:  # 15 min window
                        min_diff = diff
                        delta = Decimal(str(oi_values[i])) if oi_values[i] else Decimal("0")
            oi_deltas.append(delta)

        # Calculate heatmap snapshots
        logger.info("Calculating time-evolving heatmap...")

        snapshots = calculate_time_evolving_heatmap(
            candles=candles,
            oi_deltas=oi_deltas,
            symbol=symbol,
            price_bucket_size=Decimal(str(price_bin_size)),
        )

        stats["snapshots_generated"] = len(snapshots)
        logger.info(f"Generated {len(snapshots)} snapshots")

        if not dry_run and snapshots:
            # Persist snapshots in batches
            logger.info(f"Persisting snapshots to database (batch size: {batch_size})...")

            for i in range(0, len(snapshots), batch_size):
                batch = snapshots[i : i + batch_size]
                for snapshot in batch:
                    try:
                        db_service.save_snapshot(snapshot)
                        stats["snapshots_persisted"] += 1
                    except Exception as e:
                        stats["errors"].append(
                            f"Failed to save snapshot at {snapshot.timestamp}: {e}"
                        )
                        logger.warning(f"Failed to save snapshot: {e}")

                # Progress update
                progress = min(i + batch_size, len(snapshots))
                logger.info(f"  Persisted {progress}/{len(snapshots)} snapshots")

            logger.info(f"Persistence complete: {stats['snapshots_persisted']} snapshots saved")

    except Exception as e:
        stats["errors"].append(f"Computation failed: {e}")
        logger.error(f"Computation failed: {e}")
        raise

    stats["total_time_ms"] = (time.perf_counter() - computation_start) * 1000
    logger.info(f"Total time: {stats['total_time_ms']:.2f}ms")

    return stats


def main():
    """Main entry point."""
    args = parse_args()

    # Determine date range
    if args.start:
        start_time = parse_date(args.start)
    else:
        start_time = datetime.now() - timedelta(days=args.days)

    if args.end:
        end_time = parse_date(args.end)
    else:
        end_time = datetime.now()

    # Validate
    if start_time >= end_time:
        logger.error(f"Start time must be before end time: {start_time} >= {end_time}")
        sys.exit(1)

    # Check database exists
    db_path = Path(args.db_path)
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        logger.error("Run data ingestion first or specify correct --db-path")
        sys.exit(1)

    try:
        stats = precompute_heatmap(
            symbol=args.symbol,
            start_time=start_time,
            end_time=end_time,
            interval=args.interval,
            price_bin_size=args.price_bin_size,
            db_path=str(args.db_path),
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

        # Print summary
        print("\n" + "=" * 60)
        print("PRE-COMPUTATION SUMMARY")
        print("=" * 60)
        print(f"Symbol:              {args.symbol}")
        print(f"Time range:          {start_time} to {end_time}")
        print(f"Interval:            {args.interval}")
        print(f"Snapshots generated: {stats['snapshots_generated']}")
        print(f"Snapshots persisted: {stats['snapshots_persisted']}")
        print(f"Total time:          {stats['total_time_ms']:.2f}ms")

        if stats["errors"]:
            print(f"\nErrors ({len(stats['errors'])}):")
            for error in stats["errors"][:5]:
                print(f"  - {error}")
            if len(stats["errors"]) > 5:
                print(f"  ... and {len(stats['errors']) - 5} more")

        print("=" * 60)

        if stats["errors"]:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
