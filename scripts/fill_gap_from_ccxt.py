#!/usr/bin/env python3
"""
Bridge ccxt-data-pipeline Parquet -> DuckDB gap fill (T-2 -> T-0).

After CSV ingestion (which has ~2 day latency), reads recent Parquet files
from ccxt-data-pipeline catalog and fills the gap up to T-0.

Handles: klines (5m OHLCV), open interest, funding rate.
Venue: BINANCE only (consistent with CSV pipeline).
Dedup: INSERT OR IGNORE for klines (PK exists), anti-join for OI/funding (no UNIQUE).

Usage:
    uv run python scripts/fill_gap_from_ccxt.py --symbols BTCUSDT ETHUSDT
    uv run python scripts/fill_gap_from_ccxt.py --symbols BTCUSDT --dry-run
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("fill_gap")

DEFAULT_DB = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb"
DEFAULT_CATALOG = "/media/sam/1TB/ccxt-data-pipeline/data/catalog"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
VENUE = "BINANCE"


def parquet_glob(catalog: str, data_type: str, symbol: str) -> str:
    """Build glob path for ccxt-data-pipeline Parquet files."""
    return f"{catalog}/{data_type}/{symbol}-PERP.{VENUE}/*.parquet"


def get_watermark(con: duckdb.DuckDBPyConnection, table: str, ts_col: str, symbol: str):
    """Get MAX timestamp for a symbol in a table (the watermark)."""
    result = con.execute(f"SELECT MAX({ts_col}) FROM {table} WHERE symbol = ?", [symbol]).fetchone()
    return result[0] if result and result[0] else None


def fill_klines(con: duckdb.DuckDBPyConnection, catalog: str, symbol: str, dry_run: bool) -> dict:
    """Fill klines_5m_history gap from OHLCV Parquet files."""
    glob_path = parquet_glob(catalog, "ohlcv", symbol)
    watermark = get_watermark(con, "klines_5m_history", "open_time", symbol)

    if watermark is None:
        log.warning("  No existing klines for %s, skipping (need CSV baseline first)", symbol)
        return {"inserted": 0, "skipped": "no_baseline"}

    log.info("  Klines watermark for %s: %s", symbol, watermark)

    # Count available Parquet rows after watermark
    try:
        avail = con.execute(f"""
            SELECT COUNT(*) FROM read_parquet('{glob_path}')
            WHERE venue = '{VENUE}'
              AND timeframe = '5m'
              AND timestamp > TIMESTAMP '{watermark}'
        """).fetchone()[0]
    except Exception as e:
        log.warning("  No Parquet files found for klines %s: %s", symbol, e)
        return {"inserted": 0, "skipped": "no_parquet"}

    if avail == 0:
        log.info("  No new klines data after watermark")
        return {"inserted": 0, "skipped": "up_to_date"}

    log.info("  Found %d Parquet rows to fill for %s klines", avail, symbol)

    if dry_run:
        return {"inserted": 0, "available": avail, "skipped": "dry_run"}

    count_before = con.execute(
        "SELECT COUNT(*) FROM klines_5m_history WHERE symbol = ?", [symbol]
    ).fetchone()[0]

    # INSERT OR IGNORE: PK (open_time, symbol) handles dedup
    con.execute(f"""
        INSERT OR IGNORE INTO klines_5m_history
            (open_time, symbol, open, high, low, close, volume,
             close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume)
        SELECT
            timezone('UTC', timestamp)::TIMESTAMP AS open_time,
            REPLACE(symbol, '-PERP', '') AS symbol,
            CAST(open AS DECIMAL(18, 8)),
            CAST(high AS DECIMAL(18, 8)),
            CAST(low AS DECIMAL(18, 8)),
            CAST(close AS DECIMAL(18, 8)),
            CAST(volume AS DECIMAL(18, 8)),
            (timezone('UTC', timestamp)::TIMESTAMP + INTERVAL '5 minutes') AS close_time,
            NULL AS quote_volume,
            NULL AS count,
            NULL AS taker_buy_volume,
            NULL AS taker_buy_quote_volume
        FROM read_parquet('{glob_path}')
        WHERE venue = '{VENUE}'
          AND timeframe = '5m'
          AND timestamp > TIMESTAMP WITH TIME ZONE '{watermark} UTC'
    """)

    count_after = con.execute(
        "SELECT COUNT(*) FROM klines_5m_history WHERE symbol = ?", [symbol]
    ).fetchone()[0]

    inserted = count_after - count_before
    log.info("  Klines %s: %d inserted, %d duplicates ignored", symbol, inserted, avail - inserted)
    return {"inserted": inserted, "duplicates": avail - inserted}


def fill_open_interest(
    con: duckdb.DuckDBPyConnection,
    catalog: str,
    symbol: str,
    dry_run: bool,
) -> dict:
    """Fill open_interest_history gap from OI Parquet files."""
    glob_path = parquet_glob(catalog, "open_interest", symbol)
    watermark = get_watermark(con, "open_interest_history", "timestamp", symbol)

    if watermark is None:
        log.warning("  No existing OI for %s, skipping (need CSV baseline first)", symbol)
        return {"inserted": 0, "skipped": "no_baseline"}

    log.info("  OI watermark for %s: %s", symbol, watermark)

    try:
        avail = con.execute(f"""
            SELECT COUNT(*) FROM read_parquet('{glob_path}')
            WHERE venue = '{VENUE}'
              AND timestamp > TIMESTAMP WITH TIME ZONE '{watermark} UTC'
        """).fetchone()[0]
    except Exception as e:
        log.warning("  No Parquet files found for OI %s: %s", symbol, e)
        return {"inserted": 0, "skipped": "no_parquet"}

    if avail == 0:
        log.info("  No new OI data after watermark")
        return {"inserted": 0, "skipped": "up_to_date"}

    log.info("  Found %d Parquet rows to fill for %s OI", avail, symbol)

    if dry_run:
        return {"inserted": 0, "available": avail, "skipped": "dry_run"}

    count_before = con.execute(
        "SELECT COUNT(*) FROM open_interest_history WHERE symbol = ?", [symbol]
    ).fetchone()[0]

    max_id = con.execute("SELECT COALESCE(MAX(id), 0) FROM open_interest_history").fetchone()[0]

    # Anti-join dedup: no UNIQUE constraint on this table
    con.execute(f"""
        INSERT INTO open_interest_history
            (id, timestamp, symbol, open_interest_value, open_interest_contracts, source)
        SELECT
            ROW_NUMBER() OVER (ORDER BY p_ts) + {max_id} AS id,
            p_ts AS timestamp,
            p_sym AS symbol,
            CAST(p_oiv AS DECIMAL(20, 8)) AS open_interest_value,
            CAST(p_oi AS DECIMAL(18, 8)) AS open_interest_contracts,
            'ccxt-pipeline' AS source
        FROM (
            SELECT
                timezone('UTC', p.timestamp)::TIMESTAMP AS p_ts,
                REPLACE(p.symbol, '-PERP', '') AS p_sym,
                p.open_interest_value AS p_oiv,
                p.open_interest AS p_oi
            FROM read_parquet('{glob_path}') p
            WHERE p.venue = '{VENUE}'
              AND p.timestamp > TIMESTAMP WITH TIME ZONE '{watermark} UTC'
        ) sub
        WHERE NOT EXISTS (
            SELECT 1 FROM open_interest_history h
            WHERE h.timestamp = sub.p_ts AND h.symbol = sub.p_sym
        )
    """)

    count_after = con.execute(
        "SELECT COUNT(*) FROM open_interest_history WHERE symbol = ?", [symbol]
    ).fetchone()[0]

    inserted = count_after - count_before
    log.info("  OI %s: %d inserted, %d duplicates skipped", symbol, inserted, avail - inserted)
    return {"inserted": inserted, "duplicates": avail - inserted}


def fill_funding_rate(
    con: duckdb.DuckDBPyConnection,
    catalog: str,
    symbol: str,
    dry_run: bool,
) -> dict:
    """Fill funding_rate_history gap from funding rate Parquet files."""
    glob_path = parquet_glob(catalog, "funding_rate", symbol)
    watermark = get_watermark(con, "funding_rate_history", "timestamp", symbol)

    if watermark is None:
        log.warning("  No existing funding rate for %s, skipping (need CSV baseline first)", symbol)
        return {"inserted": 0, "skipped": "no_baseline"}

    log.info("  Funding rate watermark for %s: %s", symbol, watermark)

    try:
        avail = con.execute(f"""
            SELECT COUNT(*) FROM read_parquet('{glob_path}')
            WHERE venue = '{VENUE}'
              AND timestamp > TIMESTAMP WITH TIME ZONE '{watermark} UTC'
        """).fetchone()[0]
    except Exception as e:
        log.warning("  No Parquet files found for funding rate %s: %s", symbol, e)
        return {"inserted": 0, "skipped": "no_parquet"}

    if avail == 0:
        log.info("  No new funding rate data after watermark")
        return {"inserted": 0, "skipped": "up_to_date"}

    log.info("  Found %d Parquet rows to fill for %s funding rate", avail, symbol)

    if dry_run:
        return {"inserted": 0, "available": avail, "skipped": "dry_run"}

    count_before = con.execute(
        "SELECT COUNT(*) FROM funding_rate_history WHERE symbol = ?", [symbol]
    ).fetchone()[0]

    max_id = con.execute("SELECT COALESCE(MAX(id), 0) FROM funding_rate_history").fetchone()[0]

    # Anti-join dedup: no UNIQUE constraint on this table
    con.execute(f"""
        INSERT INTO funding_rate_history
            (id, timestamp, symbol, funding_rate, funding_interval_hours)
        SELECT
            ROW_NUMBER() OVER (ORDER BY p_ts) + {max_id} AS id,
            p_ts AS timestamp,
            p_sym AS symbol,
            CAST(p_fr AS DECIMAL(10, 8)) AS funding_rate,
            8 AS funding_interval_hours
        FROM (
            SELECT
                timezone('UTC', p.timestamp)::TIMESTAMP AS p_ts,
                REPLACE(p.symbol, '-PERP', '') AS p_sym,
                p.funding_rate AS p_fr
            FROM read_parquet('{glob_path}') p
            WHERE p.venue = '{VENUE}'
              AND p.timestamp > TIMESTAMP WITH TIME ZONE '{watermark} UTC'
        ) sub
        WHERE NOT EXISTS (
            SELECT 1 FROM funding_rate_history h
            WHERE h.timestamp = sub.p_ts AND h.symbol = sub.p_sym
        )
    """)

    count_after = con.execute(
        "SELECT COUNT(*) FROM funding_rate_history WHERE symbol = ?", [symbol]
    ).fetchone()[0]

    inserted = count_after - count_before
    log.info(
        "  Funding rate %s: %d inserted, %d duplicates skipped",
        symbol,
        inserted,
        avail - inserted,
    )
    return {"inserted": inserted, "duplicates": avail - inserted}


def validate_gaps(con: duckdb.DuckDBPyConnection, symbol: str, watermark_ts):
    """Check for gaps in klines_5m after the original watermark (warning only)."""
    if watermark_ts is None:
        return

    result = con.execute(
        """
        SELECT COUNT(*) as gaps FROM (
            SELECT open_time,
                   LEAD(open_time) OVER (ORDER BY open_time) AS next_time
            FROM klines_5m_history
            WHERE symbol = ? AND open_time >= ?
        ) WHERE EXTRACT(EPOCH FROM (next_time - open_time)) > 300 * 1.5
    """,
        [symbol, watermark_ts],
    ).fetchone()[0]

    if result > 0:
        log.warning(
            "  Gap validation: %d gaps in klines %s after %s (may be exchange maintenance)",
            result,
            symbol,
            watermark_ts,
        )
    else:
        log.info("  Gap validation: no gaps in klines %s after %s", symbol, watermark_ts)


def main():
    parser = argparse.ArgumentParser(description="Fill DuckDB gap from ccxt-data-pipeline Parquet")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS, help="Symbols to process")
    parser.add_argument("--ccxt-catalog", default=DEFAULT_CATALOG, help="Path to ccxt catalog")
    parser.add_argument("--db", default=DEFAULT_DB, help="DuckDB database path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count available data without writing",
    )
    args = parser.parse_args()

    catalog = Path(args.ccxt_catalog)
    if not catalog.is_dir():
        log.error("CCXT catalog not found: %s", catalog)
        sys.exit(1)

    db_path = Path(args.db)
    if not db_path.exists():
        log.error("DuckDB database not found: %s", db_path)
        sys.exit(1)

    log.info("Gap fill: ccxt-data-pipeline Parquet -> DuckDB")
    log.info("  Catalog: %s", catalog)
    log.info("  DB: %s", db_path)
    log.info("  Symbols: %s", args.symbols)
    log.info("  Dry run: %s", args.dry_run)

    con = duckdb.connect(str(db_path), read_only=args.dry_run)
    summary = {}

    try:
        for symbol in args.symbols:
            log.info("")
            log.info("=== Processing %s ===", symbol)
            symbol_results = {}

            # Save watermark before fill for gap validation
            klines_watermark = get_watermark(con, "klines_5m_history", "open_time", symbol)

            # Klines 5m
            log.info("--- Klines 5m ---")
            symbol_results["klines"] = fill_klines(con, str(catalog), symbol, args.dry_run)
            time.sleep(0.1)  # I/O throttle

            # Open Interest
            log.info("--- Open Interest ---")
            symbol_results["oi"] = fill_open_interest(con, str(catalog), symbol, args.dry_run)
            time.sleep(0.1)

            # Funding Rate
            log.info("--- Funding Rate ---")
            symbol_results["funding"] = fill_funding_rate(con, str(catalog), symbol, args.dry_run)
            time.sleep(0.1)

            # Gap validation (klines only, most critical)
            if not args.dry_run:
                validate_gaps(con, symbol, klines_watermark)

            summary[symbol] = symbol_results

    finally:
        con.close()

    # Print summary
    log.info("")
    log.info("=== Gap Fill Summary ===")
    total_inserted = 0
    for symbol, results in summary.items():
        for data_type, result in results.items():
            ins = result.get("inserted", 0)
            total_inserted += ins
            skip_reason = result.get("skipped", "")
            if skip_reason:
                log.info("  %s/%s: skipped (%s)", symbol, data_type, skip_reason)
            else:
                log.info("  %s/%s: %d inserted", symbol, data_type, ins)

    log.info("  Total rows inserted: %d", total_inserted)
    return 0 if total_inserted >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
