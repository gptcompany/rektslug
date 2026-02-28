#!/usr/bin/env python3
"""Initialize DuckDB database with schema from data-model.md.

Creates 6 tables:
- liquidation_levels: Calculated liquidation prices (with exchange column)
- heatmap_cache: Pre-aggregated heatmap buckets (with exchange column)
- open_interest_history: Binance Open Interest data
- funding_rate_history: 8-hour funding rates
- aggtrades_history: Actual trade events (for backtesting)
- exchange_health: Exchange adapter connection status
"""

import sys
from pathlib import Path

import duckdb

DB_PATH = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb"


def create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables and indexes."""

    # Table 1: liquidation_levels (with exchange column for multi-exchange support)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS liquidation_levels (
            id BIGINT PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            model VARCHAR(50) NOT NULL,
            price_level DECIMAL(18, 2) NOT NULL,
            liquidation_volume DECIMAL(18, 8) NOT NULL,
            leverage_tier VARCHAR(10),
            side VARCHAR(10) NOT NULL,
            confidence DECIMAL(3, 2) NOT NULL,
            exchange VARCHAR(50) DEFAULT 'binance',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_liquidation_levels_timestamp
        ON liquidation_levels(timestamp);
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_liquidation_levels_symbol_model
        ON liquidation_levels(symbol, model);
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_liquidation_levels_price
        ON liquidation_levels(price_level);
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_liquidation_levels_exchange
        ON liquidation_levels(exchange);
    """)

    print("✅ Created table: liquidation_levels (with 4 indexes)")

    # Table 2: heatmap_cache (with exchange column for multi-exchange support)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS heatmap_cache (
            id BIGINT PRIMARY KEY,
            time_bucket TIMESTAMP NOT NULL,
            price_bucket DECIMAL(18, 2) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            model VARCHAR(50) NOT NULL,
            density BIGINT NOT NULL,
            volume DECIMAL(18, 8) NOT NULL,
            exchange VARCHAR(50) DEFAULT 'binance',
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_heatmap_time_price
        ON heatmap_cache(time_bucket, price_bucket);
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_heatmap_symbol_model
        ON heatmap_cache(symbol, model);
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_heatmap_cache_exchange
        ON heatmap_cache(exchange);
    """)

    print("✅ Created table: heatmap_cache (with 3 indexes)")

    # Table 3: open_interest_history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS open_interest_history (
            id BIGINT PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            open_interest_value DECIMAL(20, 8) NOT NULL,
            open_interest_contracts DECIMAL(18, 8),
            source VARCHAR(50) DEFAULT 'binance_csv'
        );
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_oi_timestamp_symbol
        ON open_interest_history(timestamp, symbol);
    """)

    print("✅ Created table: open_interest_history (with 1 index)")

    # Table 4: funding_rate_history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS funding_rate_history (
            id BIGINT PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            funding_rate DECIMAL(10, 8) NOT NULL,
            funding_interval_hours INT DEFAULT 8
        );
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_funding_timestamp_symbol
        ON funding_rate_history(timestamp, symbol);
    """)

    print("✅ Created table: funding_rate_history (with 1 index)")

    # Table 5: aggtrades_history (COMPOSITE PK for multi-symbol/exchange support)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aggtrades_history (
            agg_trade_id BIGINT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            exchange VARCHAR(20) NOT NULL DEFAULT 'binance',
            price DECIMAL(18, 8) NOT NULL,
            quantity DECIMAL(18, 8) NOT NULL,
            side VARCHAR(4) NOT NULL,
            gross_value DOUBLE NOT NULL,
            PRIMARY KEY (agg_trade_id, symbol, exchange)
        );
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_aggtrades_timestamp_symbol
        ON aggtrades_history(timestamp, symbol);
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_aggtrades_symbol
        ON aggtrades_history(symbol);
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_aggtrades_exchange
        ON aggtrades_history(exchange);
    """)

    print("✅ Created table: aggtrades_history (with 3 indexes + composite PK)")

    # Table 6: exchange_health (T049 - monitor exchange adapter status)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exchange_health (
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
        );
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_exchange_health_exchange
        ON exchange_health(exchange);
    """)

    print("✅ Created table: exchange_health (with 1 index)")


def verify_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Verify all tables exist."""
    tables = conn.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]

    expected_tables = [
        "liquidation_levels",
        "heatmap_cache",
        "open_interest_history",
        "funding_rate_history",
        "aggtrades_history",
        "exchange_health",
    ]

    print("\n📊 Database Schema:")
    for table in expected_tables:
        if table in table_names:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  ✅ {table}: {count} rows")
        else:
            print(f"  ❌ {table}: NOT FOUND")
            sys.exit(1)


def main():
    """Initialize database schema."""
    # Ensure data directory exists
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    print(f"📥 Initializing database: {DB_PATH}")

    # Connect and create schema
    conn = duckdb.connect(DB_PATH)

    try:
        create_schema(conn)
        verify_schema(conn)
        print(f"\n✅ Database initialized successfully at {DB_PATH}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
