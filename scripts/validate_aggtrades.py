#!/usr/bin/env python3
"""Validate aggTrades data quality after ingestion.

KISS approach: SQL-based checks with rich reporting.
Run this AFTER ingestion completes to verify data integrity.

Usage:
    python /tmp/validate_aggtrades.py [--db path/to/db]
"""

import argparse
import sys

import duckdb
from rich.console import Console
from rich.table import Table

console = Console()


def validate_basic_stats(conn):
    """Check basic statistics."""
    console.print("\n[bold cyan]📊 Basic Statistics[/bold cyan]")

    stats = conn.execute("""
        SELECT
            COUNT(*) as total_rows,
            MIN(timestamp) as min_ts,
            MAX(timestamp) as max_ts,
            COUNT(DISTINCT symbol) as symbols,
            MIN(price) as min_price,
            MAX(price) as max_price
        FROM aggtrades_history
    """).fetchone()

    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Rows", f"{stats[0]:,}")
    table.add_row("Date Range", f"{stats[1]} → {stats[2]}")
    table.add_row("Symbols", str(stats[3]))
    table.add_row("Price Range", f"${stats[4]:,.2f} → ${stats[5]:,.2f}")

    console.print(table)
    return stats[0] > 0


def validate_duplicates(conn):
    """Check for duplicate trades."""
    console.print("\n[bold cyan]🔍 Duplicate Detection[/bold cyan]")

    result = conn.execute("""
        SELECT COUNT(*) as total_rows,
               COUNT(DISTINCT (timestamp, symbol, price, quantity)) as unique_rows
        FROM aggtrades_history
    """).fetchone()

    total = result[0]
    unique = result[1]
    duplicates = total - unique

    if duplicates > 0:
        console.print(f"  [red]❌ Found {duplicates:,} duplicates[/red]")

        # Show sample duplicates
        samples = conn.execute("""
            SELECT timestamp, symbol, price, quantity, COUNT(*) as count
            FROM aggtrades_history
            GROUP BY timestamp, symbol, price, quantity
            HAVING COUNT(*) > 1
            LIMIT 5
        """).fetchall()

        if samples:
            console.print("\n  Sample duplicates:")
            for row in samples:
                console.print(f"    {row[0]} {row[1]} ${row[2]} qty={row[3]} (x{row[4]})")

        return False
    else:
        console.print("  [green]✅ No duplicates found[/green]")
        return True


def validate_invalid_values(conn):
    """Check for invalid data (negative prices, zero quantity, etc.)."""
    console.print("\n[bold cyan]⚠️  Invalid Values Check[/bold cyan]")

    issues = []

    # Negative prices
    neg_price = conn.execute("SELECT COUNT(*) FROM aggtrades_history WHERE price <= 0").fetchone()[
        0
    ]
    if neg_price > 0:
        issues.append(f"Negative/zero prices: {neg_price:,}")

    # Zero quantity
    zero_qty = conn.execute(
        "SELECT COUNT(*) FROM aggtrades_history WHERE quantity <= 0"
    ).fetchone()[0]
    if zero_qty > 0:
        issues.append(f"Zero/negative quantity: {zero_qty:,}")

    # NULL values
    null_checks = {
        "timestamp": conn.execute(
            "SELECT COUNT(*) FROM aggtrades_history WHERE timestamp IS NULL"
        ).fetchone()[0],
        "price": conn.execute(
            "SELECT COUNT(*) FROM aggtrades_history WHERE price IS NULL"
        ).fetchone()[0],
        "quantity": conn.execute(
            "SELECT COUNT(*) FROM aggtrades_history WHERE quantity IS NULL"
        ).fetchone()[0],
    }

    for field, count in null_checks.items():
        if count > 0:
            issues.append(f"NULL {field}: {count:,}")

    if issues:
        console.print(f"  [red]❌ Found {len(issues)} issue types:[/red]")
        for issue in issues:
            console.print(f"    - {issue}")
        return False
    else:
        console.print("  [green]✅ All values valid[/green]")
        return True


def validate_continuity(conn):
    """Check for temporal gaps in data."""
    console.print("\n[bold cyan]📅 Temporal Continuity Check[/bold cyan]")

    # Get days with data
    days_result = conn.execute("""
        SELECT DATE(timestamp) as date, COUNT(*) as trades
        FROM aggtrades_history
        GROUP BY DATE(timestamp)
        ORDER BY date
    """).fetchall()

    if not days_result:
        console.print("  [red]❌ No data found[/red]")
        return False

    # Check for gaps
    from datetime import datetime

    gaps = []
    prev_date = None

    for row in days_result:
        current_date = datetime.strptime(str(row[0]), "%Y-%m-%d").date()

        if prev_date and (current_date - prev_date).days > 1:
            gap_days = (current_date - prev_date).days - 1
            gaps.append((prev_date, current_date, gap_days))

        prev_date = current_date

    console.print(f"  Total days with data: {len(days_result)}")

    if gaps:
        console.print(f"  [yellow]⚠️  Found {len(gaps)} gap(s):[/yellow]")
        for start, end, days in gaps[:10]:  # Show first 10
            console.print(f"    {start} → {end} ({days} days missing)")
        if len(gaps) > 10:
            console.print(f"    ... and {len(gaps) - 10} more")
        return False
    else:
        console.print("  [green]✅ No gaps detected[/green]")
        return True


def validate_sanity_checks(conn):
    """Sanity checks for realistic values."""
    console.print("\n[bold cyan]🧪 Sanity Checks[/bold cyan]")

    issues = []

    # Unrealistic prices (BTC should be between $100 and $1M typically)
    weird_prices = conn.execute("""
        SELECT COUNT(*) FROM aggtrades_history
        WHERE symbol = 'BTCUSDT' AND (price < 100 OR price > 1000000)
    """).fetchone()[0]

    if weird_prices > 0:
        sample = conn.execute("""
            SELECT timestamp, price FROM aggtrades_history
            WHERE symbol = 'BTCUSDT' AND (price < 100 OR price > 1000000)
            LIMIT 3
        """).fetchall()
        issues.append(f"Unrealistic BTC prices: {weird_prices:,} rows (sample: {sample})")

    # Huge quantities (potential data corruption)
    huge_qty = conn.execute("""
        SELECT COUNT(*) FROM aggtrades_history WHERE quantity > 10000
    """).fetchone()[0]

    if huge_qty > 0:
        issues.append(f"Very large quantities: {huge_qty:,} rows")

    if issues:
        console.print(f"  [yellow]⚠️  Found {len(issues)} potential issue(s):[/yellow]")
        for issue in issues:
            console.print(f"    - {issue}")
        return False
    else:
        console.print("  [green]✅ All sanity checks passed[/green]")
        return True


def main():
    parser = argparse.ArgumentParser(description="Validate aggTrades data quality")
    parser.add_argument("--db", default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb", help="Database path")

    args = parser.parse_args()

    console.print("\n[bold cyan]═══════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  aggTrades Data Validation Report[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════[/bold cyan]")

    console.print(f"\nDatabase: {args.db}")

    # Connect
    try:
        conn = duckdb.connect(args.db, read_only=True)
    except Exception as e:
        console.print(f"\n[bold red]❌ Cannot connect to database:[/bold red] {e}")
        sys.exit(1)

    # Run all validations
    results = {
        "Basic Stats": validate_basic_stats(conn),
        "Duplicates": validate_duplicates(conn),
        "Invalid Values": validate_invalid_values(conn),
        "Temporal Continuity": validate_continuity(conn),
        "Sanity Checks": validate_sanity_checks(conn),
    }

    conn.close()

    # Summary
    console.print("\n[bold cyan]═══ Summary ═══[/bold cyan]")
    passed = sum(results.values())
    total = len(results)

    for check, result in results.items():
        status = "[green]✅ PASS[/green]" if result else "[red]❌ FAIL[/red]"
        console.print(f"  {check}: {status}")

    console.print(f"\n[bold]Score: {passed}/{total} checks passed[/bold]")

    if passed == total:
        console.print("\n[bold green]🎉 All validation checks passed![/bold green]")
        sys.exit(0)
    else:
        console.print("\n[bold yellow]⚠️  Some checks failed - review data quality[/bold yellow]")
        sys.exit(1)


if __name__ == "__main__":
    main()
