#!/usr/bin/env python3
"""
Clean stale DuckDB lock files before ingestion.
Safe to run - only removes locks if no active writer process.
"""

import sys
from pathlib import Path


def cleanup_locks(db_path: str) -> dict:
    """
    Remove stale DuckDB lock files if safe.

    Returns:
        dict with status and details
    """
    db_path = Path(db_path)
    result = {"db_path": str(db_path), "cleaned": [], "skipped": [], "errors": []}

    # DuckDB lock file patterns
    lock_patterns = [
        db_path.with_suffix(".duckdb.wal"),
        db_path.with_suffix(".duckdb.tmp"),
        db_path.parent / f".{db_path.name}.lock",
    ]

    for lock_file in lock_patterns:
        if lock_file.exists():
            try:
                # Check if file is actually in use
                # Try to open exclusively - if it works, file is stale
                try:
                    with open(lock_file, "r+b") as f:
                        import fcntl

                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    # If we got here, lock is stale - safe to remove
                    lock_file.unlink()
                    result["cleaned"].append(str(lock_file))
                except (IOError, OSError):
                    # File is actively locked by another process
                    result["skipped"].append(str(lock_file))
            except Exception as e:
                result["errors"].append(f"{lock_file}: {e}")

    return result


def main():
    db_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb"
    )

    print(f"Cleaning DuckDB locks for: {db_path}")
    result = cleanup_locks(db_path)

    if result["cleaned"]:
        print(f"Cleaned: {', '.join(result['cleaned'])}")
    if result["skipped"]:
        print(f"Skipped (active): {', '.join(result['skipped'])}")
    if result["errors"]:
        print(f"Errors: {', '.join(result['errors'])}")
        sys.exit(1)

    print("Lock cleanup complete")


if __name__ == "__main__":
    main()
