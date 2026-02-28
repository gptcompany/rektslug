#!/usr/bin/env python3
"""Ingest Open Interest metrics data using streaming approach (OOM-safe).

Similar to klines ingestion but for Open Interest CSV files.

Usage:
    python scripts/ingest_oi.py --symbol BTCUSDT --start-date 2025-10-30 --end-date 2025-11-17 \
        --data-dir /media/sam/3TB-WDC/binance-history-data-downloader/data
"""

import argparse
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
from rich.console import Console

console = Console()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_oi_files(data_dir, symbol, start_date, end_date):
    """Get OI CSV files within date range.

    Args:
        data_dir: Base data directory
        symbol: Trading pair (e.g., BTCUSDT)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Sorted list of existing CSV file paths
    """
    metrics_dir = Path(data_dir) / symbol / "metrics"

    if not metrics_dir.exists():
        raise FileNotFoundError(f"Metrics directory not found: {metrics_dir}")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    files = []
    current = start_dt

    while current <= end_dt:
        date_str = current.strftime("%Y-%m-%d")
        file_path = metrics_dir / f"{symbol}-metrics-{date_str}.csv"

        if file_path.exists():
            files.append(file_path)
        else:
            logger.debug(f"File not found (skipped): {file_path.name}")

        current += timedelta(days=1)

    logger.info(f"Found {len(files)} OI files for {symbol} ({start_date} to {end_date})")
    return sorted(files)


def load_oi_streaming(conn, data_dir, symbol, start_date, end_date, throttle_ms=100):
    """Ingest OI files one-by-one (OOM-safe).

    Args:
        conn: DuckDB connection
        data_dir: Base data directory
        symbol: Trading pair
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        throttle_ms: Sleep time between files (ms)

    Returns:
        Total number of rows inserted
    """
    logger.info(f"Starting streaming OI ingestion for {symbol}")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"I/O throttle: {throttle_ms}ms between files")

    files = get_oi_files(data_dir, symbol, start_date, end_date)

    if not files:
        logger.warning(f"No OI files found for {symbol}")
        return 0

    # Get initial count for reporting
    initial_count = conn.execute("SELECT COUNT(*) FROM open_interest_history").fetchone()[0]
    logger.info(f"Starting from {initial_count:,} existing rows")

    # Process files one by one
    total_rows = 0
    success_count = 0
    skip_count = 0

    for idx, file_path in enumerate(files, 1):
        try:
            # Count rows in CSV before INSERT
            csv_rows = conn.execute(f"""
                SELECT COUNT(*) FROM read_csv('{file_path}', auto_detect=true, header=true)
            """).fetchone()[0]

            # Get max ID first
            max_id = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM open_interest_history"
            ).fetchone()[0]

            conn.execute(f"""
                INSERT OR IGNORE INTO open_interest_history
                (id, timestamp, symbol, open_interest_value, open_interest_contracts)
                SELECT
                    ROW_NUMBER() OVER () + {max_id} AS id,
                    CAST(create_time AS TIMESTAMP) AS timestamp,
                    symbol,
                    CAST(sum_open_interest_value AS DECIMAL(20, 8)) AS open_interest_value,
                    CAST(sum_open_interest AS DECIMAL(20, 8)) AS open_interest_contracts
                FROM read_csv('{file_path}', auto_detect=true, header=true)
                WHERE symbol = '{symbol}'
            """)

            # Count rows inserted from this file
            current_count = conn.execute("SELECT COUNT(*) FROM open_interest_history").fetchone()[0]
            file_rows = current_count - (initial_count + total_rows)
            skipped_rows = csv_rows - file_rows
            total_rows += file_rows
            success_count += 1

            logger.info(
                f"[{idx}/{len(files)}] {file_path.name}: {file_rows:,} inserted, {skipped_rows:,} skipped"
            )

            # I/O throttle to prevent HDD overload
            if throttle_ms > 0:
                time.sleep(throttle_ms / 1000.0)

        except Exception as e:
            logger.error(f"[{idx}/{len(files)}] ❌ Error processing {file_path.name}: {e}")
            skip_count += 1
            continue

    logger.info(f"\n✅ Completed: {success_count} files processed, {skip_count} failed")
    logger.info(f"📊 Total rows inserted: {total_rows:,}")

    return total_rows


def main():
    parser = argparse.ArgumentParser(description="Ingest Open Interest data (streaming, OOM-safe)")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair symbol")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--data-dir", required=True, help="Data directory path")
    parser.add_argument("--db", default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb", help="Database path")
    parser.add_argument("--throttle-ms", type=int, default=100, help="I/O throttle (ms)")

    args = parser.parse_args()

    console.print("\n[bold cyan]Open Interest Streaming Ingestion[/bold cyan]")
    console.print(f"Symbol: {args.symbol}")
    console.print(f"Date range: {args.start_date} to {args.end_date}")
    console.print(f"Database: {args.db}")
    console.print(f"I/O throttle: {args.throttle_ms}ms\n")

    # Connect to DB
    conn = duckdb.connect(args.db)

    # Ingest
    try:
        total = load_oi_streaming(
            conn,
            Path(args.data_dir),
            args.symbol,
            args.start_date,
            args.end_date,
            throttle_ms=args.throttle_ms,
        )

        console.print(f"\n✅ [bold green]Complete![/bold green] Inserted {total:,} rows")

        # Verify
        count = conn.execute("SELECT COUNT(*) FROM open_interest_history").fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM open_interest_history"
        ).fetchone()
        console.print("\nDatabase stats:")
        console.print(f"  Total rows: {count:,}")
        console.print(f"  Date range: {date_range[0]} → {date_range[1]}")

    except Exception as e:
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
