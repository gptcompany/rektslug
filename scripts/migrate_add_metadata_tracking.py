#!/usr/bin/env python3
"""Add ingestion_log table for metadata tracking.

Tracks which files have been processed, when, and with what result.
Enables troubleshooting and incremental update detection.

Usage:
    python scripts/migrate_add_metadata_tracking.py [--db path/to/db]
"""

import argparse
import sys

import duckdb
from rich.console import Console

console = Console()


def create_ingestion_log_table(conn):
    """Create ingestion_log metadata table."""
    console.print("\n[cyan]Creating ingestion_log table...[/cyan]")

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_log (
                file_path VARCHAR PRIMARY KEY,
                symbol VARCHAR NOT NULL,
                processed_at TIMESTAMP NOT NULL,
                row_count BIGINT NOT NULL,
                status VARCHAR NOT NULL,  -- 'success', 'failed', 'partial'
                error_message VARCHAR,
                file_size_bytes BIGINT,
                processing_time_ms BIGINT
            )
        """)

        console.print("  ✅ Table created successfully")
        return True

    except Exception as e:
        console.print(f"  ❌ Error: {e}")
        return False


def verify_table(conn):
    """Verify table exists and show stats."""
    console.print("\n[cyan]Verifying table...[/cyan]")

    # Check table exists
    result = conn.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = 'ingestion_log'
    """).fetchone()

    if result[0] == 0:
        console.print("  ❌ Table not found")
        return False

    # Show existing records
    count = conn.execute("SELECT COUNT(*) FROM ingestion_log").fetchone()[0]
    console.print(f"  ✅ Table exists with {count} records")

    if count > 0:
        # Show sample
        sample = conn.execute("""
            SELECT file_path, symbol, processed_at, row_count, status
            FROM ingestion_log
            ORDER BY processed_at DESC
            LIMIT 5
        """).fetchall()

        console.print("\n  Recent entries:")
        for row in sample:
            console.print(f"    {row[0]} - {row[3]:,} rows - {row[4]}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Add ingestion_log metadata table")
    parser.add_argument("--db", default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb", help="Database path")

    args = parser.parse_args()

    console.print("\n[bold cyan]═══════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  Metadata Tracking Migration[/bold cyan]")
    console.print("[bold cyan]  Add ingestion_log Table[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════[/bold cyan]")

    console.print(f"\nDatabase: {args.db}")

    # Connect
    try:
        conn = duckdb.connect(args.db)
    except Exception as e:
        console.print(f"\n[bold red]❌ Cannot connect to database:[/bold red] {e}")
        sys.exit(1)

    # Create table
    if not create_ingestion_log_table(conn):
        console.print("\n[bold red]❌ Migration failed[/bold red]")
        conn.close()
        sys.exit(1)

    # Verify
    if not verify_table(conn):
        console.print("\n[bold red]❌ Verification failed[/bold red]")
        conn.close()
        sys.exit(1)

    conn.close()

    console.print("\n[bold green]✅ Migration complete![/bold green]")
    console.print("\n💡 [cyan]Next steps:[/cyan]")
    console.print("  1. Update aggtrades_streaming.py to log metadata")
    console.print("  2. Re-run ingestion to populate table")
    console.print("  3. Query ingestion_log for troubleshooting")


if __name__ == "__main__":
    main()
