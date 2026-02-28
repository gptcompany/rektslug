#!/usr/bin/env python3
"""Ingest 15m klines (candles) using streaming approach (OOM-safe).

Similar to aggtrades ingestion but for klines data.
Handles both old format (no header) and new format (with header).

Usage:
    python scripts/ingest_klines_15m.py --symbol BTCUSDT --start-date 2024-01-01 --end-date 2024-12-31 \\
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


def get_klines_files(data_dir, symbol, start_date, end_date, interval="15m"):
    """Get klines CSV files within date range.

    Args:
        data_dir: Base data directory
        symbol: Trading pair (e.g., BTCUSDT)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        interval: Candle interval (default: 15m)

    Returns:
        Sorted list of existing CSV file paths
    """
    klines_dir = Path(data_dir) / symbol / "klines" / interval

    if not klines_dir.exists():
        raise FileNotFoundError(f"Klines directory not found: {klines_dir}")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    files = []
    current = start_dt

    while current <= end_dt:
        date_str = current.strftime("%Y-%m-%d")
        file_path = klines_dir / f"{symbol}-{interval}-{date_str}.csv"

        if file_path.exists():
            files.append(file_path)
        else:
            logger.debug(f"File not found (skipped): {file_path.name}")

        current += timedelta(days=1)

    logger.info(f"Found {len(files)} klines files for {symbol} ({start_date} to {end_date})")
    return sorted(files)


def create_klines_table(conn, interval="15m"):
    """Create klines_<interval>_history table if not exists."""
    table_name = f"klines_{interval}_history"
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            open_time TIMESTAMP NOT NULL,
            symbol VARCHAR NOT NULL,
            open DECIMAL(18, 8) NOT NULL,
            high DECIMAL(18, 8) NOT NULL,
            low DECIMAL(18, 8) NOT NULL,
            close DECIMAL(18, 8) NOT NULL,
            volume DECIMAL(18, 8) NOT NULL,
            close_time TIMESTAMP NOT NULL,
            quote_volume DECIMAL(20, 8),
            count INTEGER,
            taker_buy_volume DECIMAL(18, 8),
            taker_buy_quote_volume DECIMAL(20, 8),
            PRIMARY KEY (open_time, symbol)
        )
    """)
    logger.info(f"✅ Table {table_name} ready")


def load_klines_streaming(
    conn, data_dir, symbol, start_date, end_date, interval="15m", throttle_ms=200
):
    """Ingest klines files one-by-one with dual-format support.

    Handles both old format (no header) and new format (with header).
    Prevents OOM by streaming files individually.

    Args:
        conn: DuckDB connection
        data_dir: Base data directory
        symbol: Trading pair
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        interval: Candle interval (default: 15m)
        throttle_ms: Sleep time between files (ms) to prevent I/O overload

    Returns:
        Total number of rows inserted
    """
    logger.info(f"Starting streaming klines ingestion for {symbol}")
    logger.info(f"Interval: {interval}, Date range: {start_date} to {end_date}")
    logger.info(f"I/O throttle: {throttle_ms}ms between files")

    # Create table if not exists
    create_klines_table(conn, interval)
    table_name = f"klines_{interval}_history"

    files = get_klines_files(data_dir, symbol, start_date, end_date, interval)

    if not files:
        logger.warning(f"No klines files found for {symbol}")
        return 0

    # Get initial count for reporting
    initial_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    logger.info(f"Starting from {initial_count:,} existing rows")

    # Process files one by one
    total_rows = 0
    success_count = 0
    skip_count = 0

    for idx, file_path in enumerate(files, 1):
        try:
            # Try new format first (with header)
            csv_rows = 0
            try:
                # Count rows in CSV before INSERT
                csv_rows = conn.execute(f"""
                    SELECT COUNT(*) FROM read_csv('{file_path}', auto_detect=true, header=true)
                """).fetchone()[0]

                conn.execute(f"""
                    INSERT OR IGNORE INTO {table_name}
                    (open_time, symbol, open, high, low, close, volume, close_time,
                     quote_volume, count, taker_buy_volume, taker_buy_quote_volume)
                    SELECT
                        to_timestamp(open_time / 1000) AS open_time,
                        '{symbol}' AS symbol,
                        CAST(open AS DECIMAL(18, 8)) AS open,
                        CAST(high AS DECIMAL(18, 8)) AS high,
                        CAST(low AS DECIMAL(18, 8)) AS low,
                        CAST(close AS DECIMAL(18, 8)) AS close,
                        CAST(volume AS DECIMAL(18, 8)) AS volume,
                        to_timestamp(close_time / 1000) AS close_time,
                        CAST(quote_volume AS DECIMAL(20, 8)) AS quote_volume,
                        CAST(count AS INTEGER) AS count,
                        CAST(taker_buy_volume AS DECIMAL(18, 8)) AS taker_buy_volume,
                        CAST(taker_buy_quote_volume AS DECIMAL(20, 8)) AS taker_buy_quote_volume
                    FROM read_csv('{file_path}', auto_detect=true, header=true)
                """)
                format_used = "header"

            except duckdb.BinderException as e:
                # Fallback to old format (no header)
                if "open_time" in str(e) or "open" in str(e):
                    logger.debug(f"Fallback to no-header format for {file_path.name}")

                    # Count rows in CSV before INSERT
                    csv_rows = conn.execute(f"""
                        SELECT COUNT(*) FROM read_csv('{file_path}', auto_detect=true, header=false)
                    """).fetchone()[0]

                    conn.execute(f"""
                        INSERT OR IGNORE INTO {table_name}
                        (open_time, symbol, open, high, low, close, volume, close_time,
                         quote_volume, count, taker_buy_volume, taker_buy_quote_volume)
                        SELECT
                            to_timestamp(CAST(column0 AS BIGINT) / 1000) AS open_time,
                            '{symbol}' AS symbol,
                            CAST(column1 AS DECIMAL(18, 8)) AS open,
                            CAST(column2 AS DECIMAL(18, 8)) AS high,
                            CAST(column3 AS DECIMAL(18, 8)) AS low,
                            CAST(column4 AS DECIMAL(18, 8)) AS close,
                            CAST(column5 AS DECIMAL(18, 8)) AS volume,
                            to_timestamp(CAST(column6 AS BIGINT) / 1000) AS close_time,
                            CAST(column7 AS DECIMAL(20, 8)) AS quote_volume,
                            CAST(column8 AS INTEGER) AS count,
                            CAST(column9 AS DECIMAL(18, 8)) AS taker_buy_volume,
                            CAST(column10 AS DECIMAL(20, 8)) AS taker_buy_quote_volume
                        FROM read_csv('{file_path}', auto_detect=true, header=false)
                    """)
                    format_used = "no-header"
                else:
                    raise

            # Count rows inserted from this file
            current_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            file_rows = current_count - (initial_count + total_rows)
            skipped_rows = csv_rows - file_rows
            total_rows += file_rows
            success_count += 1

            logger.info(
                f"[{idx}/{len(files)}] {file_path.name}: {file_rows:,} inserted, {skipped_rows:,} skipped (format: {format_used})"
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
    parser = argparse.ArgumentParser(description="Ingest klines data (streaming, OOM-safe)")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair symbol")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--data-dir", required=True, help="Data directory path")
    parser.add_argument(
        "--db",
        default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        help="Database path",
    )
    parser.add_argument("--interval", default="15m", help="Kline interval (5m, 15m, 1m)")
    parser.add_argument("--throttle-ms", type=int, default=200, help="I/O throttle (ms)")

    args = parser.parse_args()

    console.print(f"\n[bold cyan]{args.interval} Klines Streaming Ingestion[/bold cyan]")
    console.print(f"Symbol: {args.symbol}")
    console.print(f"Date range: {args.start_date} to {args.end_date}")
    console.print(f"Database: {args.db}")
    console.print(f"I/O throttle: {args.throttle_ms}ms\n")

    # Connect to DB
    conn = duckdb.connect(args.db)
    table_name = f"klines_{args.interval}_history"

    # Ingest
    try:
        total = load_klines_streaming(
            conn,
            Path(args.data_dir),
            args.symbol,
            args.start_date,
            args.end_date,
            interval=args.interval,
            throttle_ms=args.throttle_ms,
        )

        console.print(f"\n✅ [bold green]Complete![/bold green] Inserted {total:,} rows")

        # Verify
        count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        date_range = conn.execute(
            f"SELECT MIN(open_time), MAX(open_time) FROM {table_name}"
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
