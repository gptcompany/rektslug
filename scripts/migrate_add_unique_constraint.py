#!/usr/bin/env python3
"""Add UNIQUE constraint to aggtrades_history for duplicate prevention.

Prevents duplicates when re-running same date range (n8n workflow safe).

Usage:
    python scripts/migrate_add_unique_constraint.py [--db path/to/db]
"""

import argparse
import logging
import sys

import duckdb
from rich.console import Console

console = Console()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check_duplicates(conn):
    """Check for existing duplicates before migration."""
    console.print("\n🔍 [cyan]Checking for existing duplicates...[/cyan]")

    result = conn.execute("""
        SELECT COUNT(*) as total_rows,
               COUNT(DISTINCT (timestamp, symbol, price, quantity)) as unique_rows
        FROM aggtrades_history
    """).fetchone()

    total = result[0]
    unique = result[1]
    duplicates = total - unique

    console.print(f"  Total rows: {total:,}")
    console.print(f"  Unique rows: {unique:,}")
    console.print(f"  Duplicates: {duplicates:,}")

    return duplicates


def remove_duplicates(conn):
    """Remove duplicate rows, keeping oldest ID."""
    console.print("\n🧹 [yellow]Removing duplicates...[/yellow]")

    # Count before
    before = conn.execute("SELECT COUNT(*) FROM aggtrades_history").fetchone()[0]

    # Delete duplicates (keep MIN(id) for each unique trade)
    conn.execute("""
        DELETE FROM aggtrades_history
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM aggtrades_history
            GROUP BY timestamp, symbol, price, quantity
        )
    """)

    # Count after
    after = conn.execute("SELECT COUNT(*) FROM aggtrades_history").fetchone()[0]
    removed = before - after

    console.print(f"  Removed: {removed:,} duplicate rows")
    console.print(f"  Remaining: {after:,} rows")

    return removed


def add_unique_constraint(conn):
    """Add UNIQUE constraint to prevent future duplicates."""
    console.print("\n✨ [cyan]Adding UNIQUE constraint...[/cyan]")

    try:
        # DuckDB syntax for adding constraint
        conn.execute("""
            ALTER TABLE aggtrades_history
            ADD CONSTRAINT unique_trade
            UNIQUE (timestamp, symbol, price, quantity)
        """)

        console.print("  ✅ UNIQUE constraint added successfully")
        return True

    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            console.print("  ℹ️  Constraint already exists")
            return True
        else:
            console.print(f"  ❌ Error: {e}")
            return False


def verify_constraint(conn):
    """Verify constraint was added."""
    console.print("\n🔬 [cyan]Verifying constraint...[/cyan]")

    # Try to insert duplicate - should fail
    try:
        # Get sample row
        sample = conn.execute("""
            SELECT timestamp, symbol, price, quantity, side, gross_value
            FROM aggtrades_history
            LIMIT 1
        """).fetchone()

        if sample:
            # Try to insert duplicate
            conn.execute(
                """
                INSERT INTO aggtrades_history
                (id, timestamp, symbol, price, quantity, side, gross_value)
                VALUES (999999999, ?, ?, ?, ?, ?, ?)
            """,
                sample,
            )

            console.print("  ❌ Constraint NOT working (duplicate inserted)")
            return False

    except Exception as e:
        if "constraint" in str(e).lower() or "unique" in str(e).lower():
            console.print("  ✅ Constraint working (duplicate rejected)")
            return True
        else:
            console.print(f"  ⚠️  Unexpected error: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="Add UNIQUE constraint to aggtrades_history")
    parser.add_argument("--db", default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb", help="Database path")
    parser.add_argument("--skip-dedup", action="store_true", help="Skip duplicate removal")

    args = parser.parse_args()

    console.print("\n[bold cyan]═══════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  aggtrades_history Migration[/bold cyan]")
    console.print("[bold cyan]  Add UNIQUE Constraint (Duplicate Prevention)[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════[/bold cyan]")

    console.print(f"\nDatabase: {args.db}")

    # Connect
    try:
        conn = duckdb.connect(args.db)
    except Exception as e:
        console.print(f"\n[bold red]❌ Cannot connect to database:[/bold red] {e}")
        sys.exit(1)

    # Check current state
    duplicates = check_duplicates(conn)

    # Remove duplicates if found
    if duplicates > 0 and not args.skip_dedup:
        confirm = console.input(f"\n⚠️  Found {duplicates:,} duplicates. Remove them? [y/N]: ")
        if confirm.lower() == "y":
            removed = remove_duplicates(conn)
            logger.info(f"Removed {removed:,} duplicate rows")
        else:
            console.print("[yellow]Skipping duplicate removal[/yellow]")
    elif duplicates == 0:
        console.print("  ✅ No duplicates found")

    # Add constraint
    success = add_unique_constraint(conn)

    if not success:
        console.print("\n[bold red]❌ Migration failed[/bold red]")
        conn.close()
        sys.exit(1)

    # Verify
    verify_constraint(conn)

    # Final stats
    console.print("\n📊 [cyan]Final database stats:[/cyan]")
    count = conn.execute("SELECT COUNT(*) FROM aggtrades_history").fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM aggtrades_history"
    ).fetchone()

    console.print(f"  Total rows: {count:,}")
    if date_range[0]:
        console.print(f"  Date range: {date_range[0]} → {date_range[1]}")

    conn.close()

    console.print("\n[bold green]✅ Migration complete![/bold green]")
    console.print("\n💡 [cyan]Next steps:[/cyan]")
    console.print("  1. Update aggtrades_streaming.py to use ON CONFLICT")
    console.print("  2. Test with duplicate data to verify")
    console.print("  3. Deploy to n8n workflow")


if __name__ == "__main__":
    main()
