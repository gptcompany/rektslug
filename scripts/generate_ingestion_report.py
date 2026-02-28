#!/usr/bin/env python3
"""Generate ingestion summary report after completion.

Creates both human-readable and JSON reports with:
- Row counts and date ranges
- Ingestion performance stats
- Gap detection
- File recommendations

Usage:
    python scripts/generate_ingestion_report.py [--db path] [--output report.json]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb
from rich.console import Console
from rich.table import Table

console = Console()


def collect_stats(conn):
    """Collect database statistics."""
    stats = {}

    # Basic counts
    result = conn.execute("""
        SELECT
            COUNT(*) as total_rows,
            MIN(timestamp) as min_ts,
            MAX(timestamp) as max_ts,
            COUNT(DISTINCT symbol) as symbols,
            MIN(price) as min_price,
            MAX(price) as max_price,
            SUM(gross_value) as total_volume
        FROM aggtrades_history
    """).fetchone()

    stats["total_rows"] = result[0]
    stats["date_range"] = {"start": str(result[1]), "end": str(result[2])}
    stats["symbols"] = result[3]
    stats["price_range"] = {
        "min": float(result[4]) if result[4] else 0,
        "max": float(result[5]) if result[5] else 0,
    }
    stats["total_volume_usd"] = float(result[6]) if result[6] else 0

    # Daily breakdown
    daily_stats = conn.execute("""
        SELECT
            DATE(timestamp) as date,
            COUNT(*) as row_count,
            MIN(price) as min_price,
            MAX(price) as max_price
        FROM aggtrades_history
        GROUP BY DATE(timestamp)
        ORDER BY date
    """).fetchall()

    stats["daily_count"] = len(daily_stats)
    stats["avg_rows_per_day"] = stats["total_rows"] / max(len(daily_stats), 1)

    # Gap detection
    gaps = []
    prev_date = None
    for row in daily_stats:
        current_date = datetime.strptime(str(row[0]), "%Y-%m-%d").date()
        if prev_date and (current_date - prev_date).days > 1:
            gap_days = (current_date - prev_date).days - 1
            gaps.append(
                {"start": str(prev_date), "end": str(current_date), "missing_days": gap_days}
            )
        prev_date = current_date

    stats["gaps"] = gaps
    stats["gap_count"] = len(gaps)

    return stats


def generate_human_report(stats):
    """Generate human-readable report."""
    console.print("\n[bold cyan]═══════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  Ingestion Summary Report[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════[/bold cyan]")

    # Basic stats table
    table = Table(title="Database Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Rows", f"{stats['total_rows']:,}")
    table.add_row("Date Range", f"{stats['date_range']['start']} → {stats['date_range']['end']}")
    table.add_row("Days with Data", f"{stats['daily_count']:,}")
    table.add_row("Avg Rows/Day", f"{stats['avg_rows_per_day']:,.0f}")
    table.add_row(
        "Price Range", f"${stats['price_range']['min']:,.2f} - ${stats['price_range']['max']:,.2f}"
    )
    table.add_row("Total Volume", f"${stats['total_volume_usd']:,.2f}")

    console.print(table)

    # Gaps
    if stats["gaps"]:
        console.print(f"\n[yellow]⚠️  Found {stats['gap_count']} gap(s) in data:[/yellow]")
        gap_table = Table()
        gap_table.add_column("Start Date", style="yellow")
        gap_table.add_column("End Date", style="yellow")
        gap_table.add_column("Missing Days", style="red")

        for gap in stats["gaps"][:10]:  # Show first 10
            gap_table.add_row(gap["start"], gap["end"], str(gap["missing_days"]))

        console.print(gap_table)

        if stats["gap_count"] > 10:
            console.print(f"  ... and {stats['gap_count'] - 10} more gaps")
    else:
        console.print("\n[green]✅ No gaps detected - continuous data[/green]")


def save_json_report(stats, output_path):
    """Save JSON report with metadata."""
    report = {
        "generated_at": datetime.now().isoformat(),
        "statistics": stats,
        "recommendations": [],
    }

    # Add recommendations
    if stats["gap_count"] > 0:
        report["recommendations"].append(
            {
                "type": "gaps",
                "severity": "warning",
                "message": f"Found {stats['gap_count']} gap(s) in data. Consider re-running ingestion for missing dates.",
                "gaps": stats["gaps"],
            }
        )

    if stats["total_rows"] == 0:
        report["recommendations"].append(
            {
                "type": "empty_database",
                "severity": "critical",
                "message": "Database is empty. Run ingestion first.",
            }
        )

    # Estimate DB size
    if stats["total_rows"] > 0:
        est_gb = (stats["total_rows"] * 100) / (1024**3)  # Rough estimate: 100 bytes/row
        report["estimated_db_size_gb"] = round(est_gb, 2)

        if est_gb > 200:
            report["recommendations"].append(
                {
                    "type": "disk_space",
                    "severity": "info",
                    "message": f"Database is large ({est_gb:.1f}GB estimated). Consider archiving old data.",
                }
            )

    # Write file
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    console.print(f"\n💾 [cyan]JSON report saved:[/cyan] {output_path}")
    return report


def main():
    parser = argparse.ArgumentParser(description="Generate ingestion summary report")
    parser.add_argument("--db", default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb", help="Database path")
    parser.add_argument(
        "--output", default="data/processed/ingestion_report.json", help="JSON output path"
    )
    parser.add_argument("--no-json", action="store_true", help="Skip JSON output")

    args = parser.parse_args()

    # Connect (read-only)
    try:
        conn = duckdb.connect(args.db, read_only=True)
    except Exception as e:
        console.print(f"\n[bold red]❌ Cannot connect to database:[/bold red] {e}")
        sys.exit(1)

    # Collect stats
    console.print("\n[cyan]Analyzing database...[/cyan]")
    stats = collect_stats(conn)
    conn.close()

    # Generate reports
    generate_human_report(stats)

    if not args.no_json:
        save_json_report(stats, args.output)

    # Summary
    console.print("\n[bold green]✅ Report generation complete![/bold green]")

    if stats["gap_count"] > 0:
        console.print(
            f"\n💡 [yellow]Next step:[/yellow] Re-run ingestion for {stats['gap_count']} missing date range(s)"
        )
        sys.exit(1)  # Exit 1 if gaps found
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
