#!/usr/bin/env python3
"""Ingest Funding Rate data using streaming approach (OOM-safe).

Funding rate files are MONTHLY (not daily like OI/klines).
Format: BTCUSDT-fundingRate-2024-01.csv

Usage:
    python scripts/ingest_funding_rate.py --symbol BTCUSDT --start-month 2020-01 --end-month 2025-11 \
        --data-dir /media/sam/3TB-WDC/binance-history-data-downloader/data
"""

import argparse
import logging
import time
from datetime import datetime
from pathlib import Path

import duckdb
from rich.console import Console

console = Console()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_funding_files(data_dir: Path, symbol: str, start_month: str, end_month: str) -> list[Path]:
    """Get funding rate CSV files within month range.

    Args:
        data_dir: Base data directory
        symbol: Trading pair (e.g., BTCUSDT)
        start_month: Start month (YYYY-MM)
        end_month: End month (YYYY-MM)

    Returns:
        Sorted list of existing CSV file paths
    """
    funding_dir = Path(data_dir) / symbol / "fundingRate"

    if not funding_dir.exists():
        raise FileNotFoundError(f"Funding rate directory not found: {funding_dir}")

    start_dt = datetime.strptime(start_month, "%Y-%m")
    end_dt = datetime.strptime(end_month, "%Y-%m")

    files = []
    current = start_dt

    while current <= end_dt:
        month_str = current.strftime("%Y-%m")
        file_path = funding_dir / f"{symbol}-fundingRate-{month_str}.csv"

        if file_path.exists():
            files.append(file_path)
        else:
            logger.debug(f"File not found (skipped): {file_path.name}")

        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    logger.info(
        f"Found {len(files)} funding rate files for {symbol} ({start_month} to {end_month})"
    )
    return sorted(files)


def load_funding_streaming(
    conn: duckdb.DuckDBPyConnection,
    data_dir: Path,
    symbol: str,
    start_month: str,
    end_month: str,
    throttle_ms: int = 100,
) -> int:
    """Ingest funding rate files one-by-one (OOM-safe).

    Args:
        conn: DuckDB connection
        data_dir: Base data directory
        symbol: Trading pair
        start_month: Start month (YYYY-MM)
        end_month: End month (YYYY-MM)
        throttle_ms: Sleep time between files (ms)

    Returns:
        Total number of rows inserted
    """
    logger.info(f"Starting streaming funding rate ingestion for {symbol}")
    logger.info(f"Month range: {start_month} to {end_month}")
    logger.info(f"I/O throttle: {throttle_ms}ms between files")

    files = get_funding_files(data_dir, symbol, start_month, end_month)

    if not files:
        logger.warning(f"No funding rate files found for {symbol}")
        return 0

    # Get initial count for reporting
    initial_count = conn.execute("SELECT COUNT(*) FROM funding_rate_history").fetchone()[0]
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
                "SELECT COALESCE(MAX(id), 0) FROM funding_rate_history"
            ).fetchone()[0]

            # Insert with deduplication based on timestamp+symbol
            conn.execute(f"""
                INSERT OR IGNORE INTO funding_rate_history
                (id, timestamp, symbol, funding_rate, funding_interval_hours)
                SELECT
                    ROW_NUMBER() OVER () + {max_id} AS id,
                    to_timestamp(CAST(calc_time AS BIGINT) / 1000) AS timestamp,
                    '{symbol}' AS symbol,
                    CAST(last_funding_rate AS DECIMAL(10, 8)) AS funding_rate,
                    CAST(funding_interval_hours AS INTEGER) AS funding_interval_hours
                FROM read_csv('{file_path}', auto_detect=true, header=true)
            """)

            # Count rows inserted from this file
            current_count = conn.execute("SELECT COUNT(*) FROM funding_rate_history").fetchone()[0]
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
            logger.error(f"[{idx}/{len(files)}] Error processing {file_path.name}: {e}")
            skip_count += 1
            continue

    logger.info(f"\nCompleted: {success_count} files processed, {skip_count} failed")
    logger.info(f"Total rows inserted: {total_rows:,}")

    return total_rows


def main():
    parser = argparse.ArgumentParser(description="Ingest Funding Rate data (streaming, OOM-safe)")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair symbol")
    parser.add_argument("--start-month", required=True, help="Start month (YYYY-MM)")
    parser.add_argument("--end-month", required=True, help="End month (YYYY-MM)")
    parser.add_argument("--data-dir", required=True, help="Data directory path")
    parser.add_argument(
        "--db",
        default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        help="Database path",
    )
    parser.add_argument("--throttle-ms", type=int, default=100, help="I/O throttle (ms)")

    args = parser.parse_args()

    console.print("\n[bold cyan]Funding Rate Streaming Ingestion[/bold cyan]")
    console.print(f"Symbol: {args.symbol}")
    console.print(f"Month range: {args.start_month} to {args.end_month}")
    console.print(f"Database: {args.db}")
    console.print(f"I/O throttle: {args.throttle_ms}ms\n")

    # Connect to DB
    conn = duckdb.connect(args.db)

    # Ingest
    try:
        total = load_funding_streaming(
            conn,
            Path(args.data_dir),
            args.symbol,
            args.start_month,
            args.end_month,
            throttle_ms=args.throttle_ms,
        )

        console.print(f"\n[bold green]Complete![/bold green] Inserted {total:,} rows")

        # Verify
        count = conn.execute("SELECT COUNT(*) FROM funding_rate_history").fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM funding_rate_history"
        ).fetchone()
        console.print("\nDatabase stats:")
        console.print(f"  Total rows: {count:,}")
        if date_range[0]:
            console.print(f"  Date range: {date_range[0]} -> {date_range[1]}")

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
