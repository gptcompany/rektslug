#!/usr/bin/env python3
"""Ingest historical Binance CSV data into DuckDB.

Usage:
    python scripts/ingest_historical.py --symbol BTCUSDT --start-date 2024-10-22 --end-date 2024-10-29
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import duckdb
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.liquidationheatmap.ingestion.csv_loader import (
    load_aggtrades_csv,
    load_csv_glob,
    load_funding_rate_csv,
    load_open_interest_csv,
)
from src.liquidationheatmap.ingestion.validators import (
    detect_outliers,
    validate_date_range,
)

# Setup logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "ingestion.log"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

console = Console()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Ingest historical Binance CSV data into DuckDB")
    parser.add_argument(
        "--symbol", type=str, default="BTCUSDT", help="Trading pair symbol (default: BTCUSDT)"
    )
    parser.add_argument("--start-date", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--db-path",
        type=str,
        default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        help="DuckDB database path",
    )
    parser.add_argument(
        "--data-dir", type=str, default="data/raw", help="Root directory for Binance CSV files"
    )
    return parser.parse_args()


def ingest_open_interest(
    conn: duckdb.DuckDBPyConnection, symbol: str, data_dir: Path, start_date: str, end_date: str
) -> int:
    """Ingest Open Interest data into DuckDB.

    Returns:
        Number of rows inserted
    """
    console.print("\n📥 [bold cyan]Ingesting Open Interest data...[/bold cyan]")

    # Build glob pattern for date range
    metrics_dir = data_dir / symbol / "metrics"
    pattern = str(metrics_dir / f"{symbol}-metrics-*.csv")

    logger.info(f"Loading Open Interest CSV files from: {pattern}")

    try:
        # Load CSV files
        df = load_csv_glob(pattern, loader_func=load_open_interest_csv, conn=conn)

        # Filter by date range
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        end = end.replace(hour=23, minute=59, second=59)  # Include entire day
        df = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)]

        if df.empty:
            logger.warning("No Open Interest data found in date range")
            return 0

        # Validate data
        expected_days = (end - start).days + 1
        if not validate_date_range(df, expected_days, tolerance=2):
            logger.warning(f"Date range validation failed. Expected ~{expected_days} days")

        # Detect outliers
        outliers = detect_outliers(df, "open_interest_value")
        if outliers:
            logger.warning(f"Detected {len(outliers)} outlier values in Open Interest data")

        # Insert into DuckDB
        # Generate sequential IDs
        # Get next available ID
        max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM open_interest_history").fetchone()[
            0
        ]
        df["id"] = range(max_id + 1, max_id + 1 + len(df))

        conn.execute("""
            INSERT OR IGNORE INTO open_interest_history
            (id, timestamp, symbol, open_interest_value, open_interest_contracts)
            SELECT id, timestamp, symbol, open_interest_value, open_interest_contracts
            FROM df
        """)

        row_count = len(df)
        console.print(f"✅ Ingested [bold green]{row_count}[/bold green] Open Interest rows")
        logger.info(f"Successfully ingested {row_count} Open Interest rows")

        return row_count

    except FileNotFoundError as e:
        logger.error(f"Open Interest CSV files not found: {e}")
        console.print(f"[bold red]❌ Error:[/bold red] CSV files not found at {metrics_dir}")
        console.print(
            "[yellow]ℹ️  This is expected if historical data hasn't been downloaded yet.[/yellow]"
        )
        return 0
    except Exception as e:
        logger.error(f"Failed to ingest Open Interest data: {e}")
        raise


def ingest_funding_rate(
    conn: duckdb.DuckDBPyConnection, symbol: str, data_dir: Path, start_date: str, end_date: str
) -> int:
    """Ingest Funding Rate data into DuckDB.

    Returns:
        Number of rows inserted
    """
    console.print("\n📥 [bold cyan]Ingesting Funding Rate data...[/bold cyan]")

    funding_dir = data_dir / symbol / "fundingRate"
    pattern = str(funding_dir / f"{symbol}-fundingRate-*.csv")

    logger.info(f"Loading Funding Rate CSV files from: {pattern}")

    try:
        # Load CSV files
        df = load_csv_glob(pattern, loader_func=load_funding_rate_csv, conn=conn)

        # Filter by date range
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        end = end.replace(hour=23, minute=59, second=59)  # Include entire day
        df = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)]

        if df.empty:
            logger.warning("No Funding Rate data found in date range")
            return 0

        # Validate data
        outliers = detect_outliers(df, "funding_rate")
        if outliers:
            logger.warning(f"Detected {len(outliers)} outlier funding rates")

        # Insert into DuckDB
        # Get next available ID
        max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM funding_rate_history").fetchone()[0]
        df["id"] = range(max_id + 1, max_id + 1 + len(df))

        conn.execute("""
            INSERT OR IGNORE INTO funding_rate_history
            (id, timestamp, symbol, funding_rate)
            SELECT id, timestamp, symbol, funding_rate
            FROM df
        """)

        row_count = len(df)
        console.print(f"✅ Ingested [bold green]{row_count}[/bold green] Funding Rate rows")
        logger.info(f"Successfully ingested {row_count} Funding Rate rows")

        return row_count

    except FileNotFoundError as e:
        logger.error(f"Funding Rate CSV files not found: {e}")
        console.print(f"[bold red]❌ Error:[/bold red] CSV files not found at {funding_dir}")
        console.print(
            "[yellow]ℹ️  This is expected if historical data hasn't been downloaded yet.[/yellow]"
        )
        return 0
    except Exception as e:
        logger.error(f"Failed to ingest Funding Rate data: {e}")
        raise


def ingest_aggtrades(
    conn: duckdb.DuckDBPyConnection, symbol: str, data_dir: Path, start_date: str, end_date: str
) -> int:
    """Ingest aggTrades data into DuckDB.

    Returns:
        Number of rows inserted
    """
    console.print("\n📥 [bold cyan]Ingesting aggTrades data...[/bold cyan]")

    aggtrades_dir = data_dir / symbol / "aggTrades"
    pattern = str(aggtrades_dir / f"{symbol}-aggTrades-*.csv")

    logger.info(f"Loading aggTrades CSV files from: {pattern}")

    try:
        df = load_csv_glob(pattern, loader_func=load_aggtrades_csv, conn=conn)

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        end = end.replace(hour=23, minute=59, second=59)
        df = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)]

        if df.empty:
            logger.warning("No aggTrades data found in date range")
            return 0

        max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM aggtrades_history").fetchone()[0]
        df["id"] = range(max_id + 1, max_id + 1 + len(df))

        conn.execute("""
            INSERT OR IGNORE INTO aggtrades_history
            (id, timestamp, symbol, price, quantity, side, gross_value)
            SELECT id, timestamp, symbol, price, quantity, side, gross_value
            FROM df
        """)

        row_count = len(df)
        console.print(f"✅ Ingested [bold green]{row_count:,}[/bold green] aggTrades rows")
        logger.info(f"Successfully ingested {row_count} aggTrades rows")

        return row_count

    except FileNotFoundError as e:
        logger.error(f"aggTrades CSV files not found: {e}")
        console.print(f"[bold red]❌ Error:[/bold red] CSV files not found at {aggtrades_dir}")
        console.print(
            "[yellow]ℹ️  This is expected if historical data hasn't been downloaded yet.[/yellow]"
        )
        return 0
    except Exception as e:
        logger.error(f"Failed to ingest aggTrades data: {e}")
        raise


def main():
    """Main ingestion workflow."""
    args = parse_args()

    console.print("\n[bold blue]═══════════════════════════════════════════[/bold blue]")
    console.print("[bold blue]  Binance Historical Data Ingestion[/bold blue]")
    console.print("[bold blue]═══════════════════════════════════════════[/bold blue]\n")

    console.print(f"Symbol: [cyan]{args.symbol}[/cyan]")
    console.print(f"Date Range: [cyan]{args.start_date}[/cyan] to [cyan]{args.end_date}[/cyan]")
    console.print(f"Database: [cyan]{args.db_path}[/cyan]\n")

    # Validate database exists
    db_path = Path(args.db_path)
    if not db_path.exists():
        console.print(f"[bold red]❌ Error:[/bold red] Database not found at {db_path}")
        console.print("[yellow]ℹ️  Run 'python scripts/init_database.py' first[/yellow]")
        sys.exit(1)

    # Connect to DuckDB
    logger.info(f"Connecting to DuckDB: {args.db_path}")
    conn = duckdb.connect(args.db_path)

    start_time = datetime.now()
    total_rows = 0

    try:
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            # Ingest Open Interest
            task1 = progress.add_task("Ingesting Open Interest...", total=None)
            oi_rows = ingest_open_interest(
                conn, args.symbol, Path(args.data_dir), args.start_date, args.end_date
            )
            progress.update(task1, completed=True)
            total_rows += oi_rows

            # Ingest Funding Rate
            task2 = progress.add_task("Ingesting Funding Rate...", total=None)
            fr_rows = ingest_funding_rate(
                conn, args.symbol, Path(args.data_dir), args.start_date, args.end_date
            )
            progress.update(task2, completed=True)
            total_rows += fr_rows

            # Ingest aggTrades
            task3 = progress.add_task("Ingesting aggTrades...", total=None)
            at_rows = ingest_aggtrades(
                conn, args.symbol, Path(args.data_dir), args.start_date, args.end_date
            )
            progress.update(task3, completed=True)
            total_rows += at_rows

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        console.print("\n[bold green]✅ Ingestion Complete![/bold green]")
        console.print(f"Total rows: [bold]{total_rows}[/bold]")
        console.print(f"Duration: [bold]{duration:.2f}s[/bold]")

        if duration > 0 and total_rows > 0:
            rate = total_rows / duration
            console.print(f"Rate: [bold]{rate:.0f} rows/sec[/bold]\n")

        logger.info(f"Ingestion complete: {total_rows} total rows in {duration:.2f}s")

    except Exception as e:
        console.print(f"\n[bold red]❌ Ingestion failed:[/bold red] {e}")
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
