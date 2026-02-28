#!/usr/bin/env python3
"""Migration script to add exchange column to liquidation tables.

T045: Create migration script
T046: Add exchange VARCHAR DEFAULT 'binance' column
T047: Add idx_liquidations_exchange index
T048: Backfill existing rows with 'binance'

This migration:
1. Adds 'exchange' column to liquidation_levels and heatmap_cache tables
2. Sets default value to 'binance' for all existing rows
3. Adds index for efficient exchange-based filtering
4. Creates exchange_health table for monitoring adapter status

Usage:
    python scripts/migrate_add_exchange_column.py [--db-path PATH]
"""

import argparse
import logging
import sys
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def migrate_add_exchange(conn: duckdb.DuckDBPyConnection) -> None:
    """Add exchange column to liquidation tables.

    Args:
        conn: Active DuckDB connection

    This migration:
    - Adds 'exchange' column with default 'binance'
    - Backfills existing rows
    - Creates index for efficient queries
    """
    logger.info("Starting exchange column migration...")

    # Check if column already exists in liquidation_levels
    columns = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'liquidation_levels' AND column_name = 'exchange'"
    ).fetchall()

    if columns:
        logger.info("Exchange column already exists in liquidation_levels, skipping")
    else:
        # Add exchange column to liquidation_levels
        logger.info("Adding exchange column to liquidation_levels...")
        conn.execute("""
            ALTER TABLE liquidation_levels
            ADD COLUMN exchange VARCHAR(50) DEFAULT 'binance'
        """)

        # Backfill existing rows (redundant due to DEFAULT, but explicit)
        conn.execute("""
            UPDATE liquidation_levels
            SET exchange = 'binance'
            WHERE exchange IS NULL
        """)

        # Add index for exchange filtering
        logger.info("Adding index on exchange column...")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_liquidation_levels_exchange
            ON liquidation_levels(exchange)
        """)

        logger.info("✅ liquidation_levels migration complete")

    # Check if column exists in heatmap_cache
    columns = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'heatmap_cache' AND column_name = 'exchange'"
    ).fetchall()

    if columns:
        logger.info("Exchange column already exists in heatmap_cache, skipping")
    else:
        # Add exchange column to heatmap_cache
        logger.info("Adding exchange column to heatmap_cache...")
        conn.execute("""
            ALTER TABLE heatmap_cache
            ADD COLUMN exchange VARCHAR(50) DEFAULT 'binance'
        """)

        # Backfill existing rows
        conn.execute("""
            UPDATE heatmap_cache
            SET exchange = 'binance'
            WHERE exchange IS NULL
        """)

        # Add index for exchange filtering
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_heatmap_cache_exchange
            ON heatmap_cache(exchange)
        """)

        logger.info("✅ heatmap_cache migration complete")

    logger.info("✅ Exchange column migration completed successfully")


def create_exchange_health_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create exchange_health table for monitoring adapter status.

    Args:
        conn: Active DuckDB connection

    T049: Creates table to track exchange connection health metrics.
    """
    logger.info("Creating exchange_health table...")

    # Check if table exists
    tables = conn.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]

    if "exchange_health" in table_names:
        logger.info("exchange_health table already exists, skipping")
        return

    conn.execute("""
        CREATE TABLE exchange_health (
            id BIGINT PRIMARY KEY,
            exchange VARCHAR(50) NOT NULL UNIQUE,
            is_connected BOOLEAN NOT NULL DEFAULT false,
            last_heartbeat TIMESTAMP,
            message_count BIGINT NOT NULL DEFAULT 0,
            error_count BIGINT NOT NULL DEFAULT 0,
            uptime_percent DECIMAL(5, 2) DEFAULT 0.0,
            last_error VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create index for exchange lookups
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_exchange_health_exchange
        ON exchange_health(exchange)
    """)

    logger.info("✅ exchange_health table created")


def run_full_migration(db_path: str) -> None:
    """Run the complete migration on the specified database.

    Args:
        db_path: Path to DuckDB database file

    Uses transaction safety: if any migration step fails, all changes are rolled back.
    """
    logger.info(f"Opening database: {db_path}")

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(db_path)

    try:
        # Begin transaction for atomic migration
        conn.execute("BEGIN TRANSACTION")

        # Run migrations
        migrate_add_exchange(conn)
        create_exchange_health_table(conn)

        # Commit only if all migrations succeeded
        conn.execute("COMMIT")
        logger.info("All migrations completed successfully")
    except Exception as e:
        # Rollback on any failure to maintain database consistency
        logger.error(f"Migration failed, rolling back: {e}")
        try:
            conn.execute("ROLLBACK")
            logger.info("Rollback completed")
        except Exception as rollback_error:
            logger.error(f"Rollback failed: {rollback_error}")
        raise
    finally:
        conn.close()


def main():
    """CLI entry point for migration script."""
    parser = argparse.ArgumentParser(description="Add exchange column to liquidation tables")
    parser.add_argument(
        "--db-path",
        default="/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        help="Path to DuckDB database (default: /media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb)",
    )
    args = parser.parse_args()

    try:
        run_full_migration(args.db_path)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
