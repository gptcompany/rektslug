#!/usr/bin/env python3
"""Generate pre-aggregated heatmap cache for fast API queries.

Usage:
    python scripts/generate_heatmap_cache.py --symbol BTCUSDT --days 7
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import duckdb
from rich.console import Console

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "heatmap_cache.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

console = Console()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Generate heatmap cache from liquidation levels")
    parser.add_argument(
        "--symbol", type=str, default="BTCUSDT", help="Trading pair symbol (default: BTCUSDT)"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to aggregate (default: 7)"
    )
    parser.add_argument(
        "--price-bucket", type=int, default=100, help="Price bucket size in dollars (default: $100)"
    )
    parser.add_argument(
        "--time-bucket",
        type=str,
        default="1h",
        choices=["1h", "4h", "12h", "1d"],
        help="Time bucket size (default: 1h)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        help="DuckDB database path",
    )
    return parser.parse_args()


def main():
    """Main heatmap cache generation workflow."""
    args = parse_args()

    console.print("\n[bold blue]═══════════════════════════════════════════[/bold blue]")
    console.print("[bold blue]  Heatmap Cache Generation[/bold blue]")
    console.print("[bold blue]═══════════════════════════════════════════[/bold blue]\n")

    console.print(f"Symbol: [cyan]{args.symbol}[/cyan]")
    console.print(f"Days: [cyan]{args.days}[/cyan]")
    console.print(f"Price bucket: [cyan]${args.price_bucket}[/cyan]")
    console.print(f"Time bucket: [cyan]{args.time_bucket}[/cyan]")
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

    try:
        # Clear existing cache for symbol
        console.print(f"\n🗑️  [cyan]Clearing existing cache for {args.symbol}...[/cyan]")
        conn.execute(f"DELETE FROM heatmap_cache WHERE symbol = '{args.symbol}'")

        # Map time bucket to DuckDB interval
        time_interval_map = {"1h": "1 hour", "4h": "4 hours", "12h": "12 hours", "1d": "1 day"}
        interval = time_interval_map[args.time_bucket]

        # Generate heatmap cache
        console.print("📊 [cyan]Aggregating liquidations into heatmap buckets...[/cyan]")
        logger.info(f"Aggregating with price_bucket=${args.price_bucket}, time_bucket={interval}")

        # Simplified aggregation (without time_bucket_gapfill for compatibility)
        sql = f"""
        INSERT INTO heatmap_cache
        SELECT
            ROW_NUMBER() OVER () AS id,
            date_trunc('hour', timestamp) AS time_bucket,
            FLOOR(price_level / {args.price_bucket}) * {args.price_bucket} AS price_bucket,
            '{args.symbol}' AS symbol,
            model,
            COUNT(*) AS density,
            SUM(liquidation_volume) AS volume,
            CURRENT_TIMESTAMP AS last_updated
        FROM liquidation_levels
        WHERE symbol = '{args.symbol}'
        GROUP BY date_trunc('hour', timestamp), price_bucket, model
        ORDER BY time_bucket, price_bucket, model
        """

        conn.execute(sql)
        rows_inserted = conn.execute(
            "SELECT COUNT(*) FROM heatmap_cache WHERE symbol = ?", [args.symbol]
        ).fetchone()[0]

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        console.print("\n[bold green]✅ Heatmap cache generated successfully![/bold green]")
        console.print(f"Rows inserted: [bold]{rows_inserted}[/bold]")
        console.print(f"Duration: [bold]{duration:.2f}s[/bold]\n")

        logger.info(f"Generated {rows_inserted} heatmap cache rows in {duration:.2f}s")

    except Exception as e:
        console.print(f"\n[bold red]❌ Cache generation failed:[/bold red] {e}")
        logger.error(f"Cache generation failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
