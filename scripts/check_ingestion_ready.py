#!/usr/bin/env python3
"""Pre-flight checks before ingestion (production-ready).

Checks:
1. Concurrent write lock available
2. Sufficient disk space
3. CSV file integrity
4. Database connectivity

KISS approach: Run this BEFORE starting ingestion.

Usage:
    python scripts/check_ingestion_ready.py --db /media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb --data-dir /path/to/data
"""

import argparse
import fcntl
import shutil
import sys
from pathlib import Path

import duckdb
from rich.console import Console

console = Console()

# Constants
MIN_DISK_SPACE_GB = 100
LOCK_FILE_PATH = "/tmp/liquidation_heatmap_ingestion.lock"


def check_lock_available():
    """Check if ingestion lock is available."""
    console.print("\n[cyan]1. Checking concurrent write lock...[/cyan]")

    try:
        lock_file = open(LOCK_FILE_PATH, "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        console.print("  ✅ Lock available (no other ingestion running)")

        # Release lock for actual ingestion
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
        return True

    except BlockingIOError:
        console.print("  ❌ Lock held (another ingestion is running)")
        console.print("     Wait for it to complete or kill the process")
        return False
    except Exception as e:
        console.print(f"  ⚠️  Lock check failed: {e}")
        return False


def check_disk_space(db_path):
    """Check available disk space."""
    console.print("\n[cyan]2. Checking disk space...[/cyan]")

    try:
        db_parent = Path(db_path).parent
        disk = shutil.disk_usage(db_parent)

        free_gb = disk.free / (1024**3)
        total_gb = disk.total / (1024**3)
        used_gb = disk.used / (1024**3)

        console.print(f"  Total: {total_gb:.1f} GB")
        console.print(f"  Used: {used_gb:.1f} GB")
        console.print(f"  Free: {free_gb:.1f} GB")

        if free_gb < MIN_DISK_SPACE_GB:
            console.print(f"  ❌ Insufficient space (need {MIN_DISK_SPACE_GB}GB minimum)")
            return False
        else:
            console.print(f"  ✅ Sufficient space ({free_gb:.1f} GB available)")
            return True

    except Exception as e:
        console.print(f"  ⚠️  Disk check failed: {e}")
        return False


def check_database_connectivity(db_path):
    """Check database is accessible."""
    console.print("\n[cyan]3. Checking database connectivity...[/cyan]")

    try:
        conn = duckdb.connect(db_path)

        # Try simple query
        result = conn.execute("SELECT COUNT(*) FROM aggtrades_history").fetchone()
        count = result[0]

        console.print(f"  ✅ Database accessible ({count:,} existing rows)")

        conn.close()
        return True

    except Exception as e:
        console.print(f"  ❌ Database error: {e}")
        return False


def check_csv_samples(data_dir, symbol="BTCUSDT", sample_count=5):
    """Validate sample CSV files for corruption."""
    console.print("\n[cyan]4. Checking CSV file integrity (sample)...[/cyan]")

    try:
        aggtrades_dir = Path(data_dir) / symbol / "aggTrades"

        if not aggtrades_dir.exists():
            console.print(f"  ❌ Directory not found: {aggtrades_dir}")
            return False

        # Get random sample of files
        csv_files = sorted(aggtrades_dir.glob("*.csv"))

        if not csv_files:
            console.print("  ⚠️  No CSV files found")
            return False

        # Sample first, middle, last files
        sample_files = [csv_files[0], csv_files[len(csv_files) // 2], csv_files[-1]][:sample_count]

        issues = []

        for file_path in sample_files:
            # Check 1: File size > 0
            size = file_path.stat().st_size
            if size == 0:
                issues.append(f"{file_path.name}: empty file")
                continue

            # Check 2: Can read first line
            try:
                with open(file_path, "r") as f:
                    first_line = f.readline()
                    if not first_line:
                        issues.append(f"{file_path.name}: no content")
            except Exception as e:
                issues.append(f"{file_path.name}: read error ({e})")

        if issues:
            console.print(f"  ❌ Found {len(issues)} corrupted file(s):")
            for issue in issues:
                console.print(f"     - {issue}")
            return False
        else:
            console.print(f"  ✅ Sampled {len(sample_files)} files - all valid")
            console.print(f"     Total CSV files: {len(csv_files)}")
            return True

    except Exception as e:
        console.print(f"  ⚠️  CSV check failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Pre-flight checks for ingestion")
    parser.add_argument("--db", required=True, help="Database path")
    parser.add_argument("--data-dir", required=True, help="Data directory")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading symbol")

    args = parser.parse_args()

    console.print("\n[bold cyan]═══════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  Ingestion Pre-Flight Checks[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════[/bold cyan]")

    # Run all checks
    results = {
        "Lock": check_lock_available(),
        "Disk Space": check_disk_space(args.db),
        "Database": check_database_connectivity(args.db),
        "CSV Files": check_csv_samples(args.data_dir, args.symbol),
    }

    # Summary
    console.print("\n[bold cyan]═══ Summary ═══[/bold cyan]")
    passed = sum(results.values())
    total = len(results)

    for check, result in results.items():
        status = "[green]✅ PASS[/green]" if result else "[red]❌ FAIL[/red]"
        console.print(f"  {check}: {status}")

    console.print(f"\n[bold]Score: {passed}/{total} checks passed[/bold]")

    if passed == total:
        console.print("\n[bold green]🎉 All checks passed - ready for ingestion![/bold green]")
        sys.exit(0)
    else:
        console.print("\n[bold red]❌ Some checks failed - fix issues before ingestion[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
