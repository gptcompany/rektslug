#!/usr/bin/env python3
"""Ingest aggTrades using streaming approach (OOM-safe).

Standalone script for aggTrades ingestion that prevents exit 137 OOM crash.
Uses file-by-file streaming instead of pandas buffering.

Usage:
    python scripts/ingest_aggtrades.py --symbol BTCUSDT --start-date 2024-01-01 --end-date 2024-01-03 \\
        --data-dir /path/to/binance-data
"""

import argparse
import logging
import sys
from pathlib import Path

import duckdb
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.liquidationheatmap.ingestion.aggtrades_streaming import load_aggtrades_streaming

console = Console()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    parser = argparse.ArgumentParser(description="Ingest aggTrades data (streaming, OOM-safe)")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair symbol")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--data-dir", required=True, help="Data directory path")
    parser.add_argument("--db", default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb", help="Database path")
    parser.add_argument("--throttle-ms", type=int, default=100, help="I/O throttle (ms)")

    args = parser.parse_args()

    console.print("\n[bold cyan]aggTrades Streaming Ingestion[/bold cyan]")
    console.print(f"Symbol: {args.symbol}")
    console.print(f"Date range: {args.start_date} to {args.end_date}")
    console.print(f"Database: {args.db}")
    console.print(f"I/O throttle: {args.throttle_ms}ms\n")

    # Connect to DB
    conn = duckdb.connect(args.db)

    # Ingest
    try:
        total = load_aggtrades_streaming(
            conn,
            Path(args.data_dir),
            args.symbol,
            args.start_date,
            args.end_date,
            throttle_ms=args.throttle_ms,
        )

        console.print(f"\n✅ [bold green]Complete![/bold green] Inserted {total:,} rows")

        # Verify
        count = conn.execute("SELECT COUNT(*) FROM aggtrades_history").fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM aggtrades_history"
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
