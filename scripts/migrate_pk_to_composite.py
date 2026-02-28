#!/usr/bin/env python3
"""Schema Migration: Change PRIMARY KEY from agg_trade_id to (agg_trade_id, symbol).

This migration fixes the critical bug where ETHUSDT data was rejected as duplicates
because agg_trade_id alone is NOT unique across symbols.

Steps:
1. Create new table with correct schema
2. Copy all existing data
3. Rename tables
4. Recreate indexes

IMPORTANT: Run this script when database is NOT in use!

Usage:
    python3 migrate_pk_to_composite.py --db /path/to/liquidations.duckdb [--dry-run]
"""

import argparse
import sys
from pathlib import Path

import duckdb


def migrate_pk_to_composite(db_path: Path, dry_run: bool = False):
    """Execute the migration."""
    print("=" * 70)
    print("  PRIMARY KEY MIGRATION: agg_trade_id -> (agg_trade_id, symbol)")
    print("=" * 70)
    print(f"Database: {db_path}")
    print(f"Dry run: {dry_run}")
    print()

    conn = duckdb.connect(str(db_path), read_only=dry_run)

    try:
        # Step 1: Check current schema
        print("[1/6] Checking current schema...")
        pk_check = conn.execute("""
            SELECT constraint_name, column_name
            FROM information_schema.key_column_usage
            WHERE table_name = 'aggtrades_history'
        """).fetchall()

        if len(pk_check) > 1:
            print("✅ Schema already has composite PRIMARY KEY. No migration needed.")
            return 0

        if pk_check and pk_check[0][1] == "agg_trade_id":
            print(f"⚠️  Current PK: {pk_check[0][1]} (needs migration)")
        else:
            print("❌ Unexpected schema state. Please check manually.")
            return 1

        # Step 2: Get current row count
        print("\n[2/6] Analyzing current data...")
        counts = conn.execute("""
            SELECT symbol, COUNT(*) as cnt
            FROM aggtrades_history
            GROUP BY symbol
        """).fetchall()

        total_rows = sum(c[1] for c in counts)
        print(f"Total rows: {total_rows:,}")
        for symbol, cnt in counts:
            print(f"  {symbol}: {cnt:,} rows")

        # Check for actual duplicates that would conflict
        print("\n[3/6] Checking for conflicting agg_trade_ids...")
        conflicts = conn.execute("""
            WITH id_counts AS (
                SELECT agg_trade_id, COUNT(DISTINCT symbol) as symbol_count
                FROM aggtrades_history
                GROUP BY agg_trade_id
            )
            SELECT COUNT(*) FROM id_counts WHERE symbol_count > 1
        """).fetchone()[0]

        if conflicts > 0:
            print(f"❌ CRITICAL: {conflicts:,} agg_trade_ids exist in MULTIPLE symbols!")
            print("   This means data was incorrectly inserted. Migration will fix this.")
        else:
            print("✅ No conflicting agg_trade_ids (each ID exists in only one symbol)")

        if dry_run:
            print("\n[DRY RUN] Would execute migration. No changes made.")
            return 0

        # Step 4: Create new table with composite PK
        print("\n[4/6] Creating new table with composite PRIMARY KEY...")
        conn.execute("""
            CREATE TABLE aggtrades_history_new (
                agg_trade_id BIGINT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                symbol VARCHAR NOT NULL,
                price DECIMAL(18, 8) NOT NULL,
                quantity DECIMAL(18, 8) NOT NULL,
                side VARCHAR NOT NULL,
                gross_value DOUBLE NOT NULL,
                PRIMARY KEY (agg_trade_id, symbol)
            )
        """)
        print("✅ New table created")

        # Step 5: Copy data (this handles duplicates by keeping first occurrence)
        print("\n[5/6] Copying data to new table...")
        copied = conn.execute("""
            INSERT INTO aggtrades_history_new
            SELECT * FROM aggtrades_history
            ON CONFLICT DO NOTHING
        """).fetchone()

        new_count = conn.execute("SELECT COUNT(*) FROM aggtrades_history_new").fetchone()[0]
        print(f"✅ Copied {new_count:,} rows (original: {total_rows:,})")

        if new_count != total_rows:
            print(f"⚠️  {total_rows - new_count:,} rows were duplicates and removed")

        # Step 6: Swap tables and recreate indexes
        print("\n[6/6] Swapping tables and recreating indexes...")
        conn.execute("DROP TABLE aggtrades_history")
        conn.execute("ALTER TABLE aggtrades_history_new RENAME TO aggtrades_history")

        # Recreate indexes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_aggtrades_timestamp_symbol
            ON aggtrades_history(timestamp, symbol)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_aggtrades_timestamp
            ON aggtrades_history(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_aggtrades_symbol
            ON aggtrades_history(symbol)
        """)
        print("✅ Tables swapped and indexes recreated")

        # Verify final state
        print("\n" + "=" * 70)
        print("  MIGRATION COMPLETE")
        print("=" * 70)

        final_pk = conn.execute("""
            SELECT constraint_name, column_name
            FROM information_schema.key_column_usage
            WHERE table_name = 'aggtrades_history'
            ORDER BY ordinal_position
        """).fetchall()

        print("New PRIMARY KEY columns:")
        for _, col in final_pk:
            print(f"  - {col}")

        final_count = conn.execute("SELECT COUNT(*) FROM aggtrades_history").fetchone()[0]
        print(f"\nFinal row count: {final_count:,}")

        return 0

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate aggtrades_history PRIMARY KEY to composite (agg_trade_id, symbol)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db",
        default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        help="Path to DuckDB database",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Check current state without making changes"
    )

    args = parser.parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    sys.exit(migrate_pk_to_composite(db_path, args.dry_run))


if __name__ == "__main__":
    main()
