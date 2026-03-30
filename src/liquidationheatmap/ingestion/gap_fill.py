"""Gap-fill logic: bridge ccxt-data-pipeline Parquet -> QuestDB.

Extracted from scripts/fill_gap_from_ccxt.py for in-process use by the API.
Handles: klines (1m + 5m OHLCV), open interest, funding rate.
Venue: BINANCE only (consistent with CSV pipeline).
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd

from src.liquidationheatmap.ingestion.questdb_service import QuestDBService

logger = logging.getLogger(__name__)


VENUE = "BINANCE"
KLINE_INTERVALS = ("5m", "1m")
# Bootstrap windows for newly introduced symbols or intervals without baseline.
# 14 days covers 1w liq-map lookback with safety margin for all hot data types.
KLINE_BOOTSTRAP_DAYS_BY_INTERVAL = {"1m": 14, "5m": 14}
OI_BOOTSTRAP_DAYS = 14
FUNDING_BOOTSTRAP_DAYS = 14


def _kline_minutes(interval: str) -> int:
    if interval.endswith("m") and interval[:-1].isdigit():
        return int(interval[:-1])
    raise ValueError(f"Unsupported kline interval: {interval}")


def _ensure_klines_table(con: duckdb.DuckDBPyConnection, interval: str) -> str:
    table_name = f"klines_{interval}_history"
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            open_time TIMESTAMP NOT NULL,
            symbol VARCHAR NOT NULL,
            open DECIMAL(18, 8) NOT NULL,
            high DECIMAL(18, 8) NOT NULL,
            low DECIMAL(18, 8) NOT NULL,
            close DECIMAL(18, 8) NOT NULL,
            volume DECIMAL(18, 8) NOT NULL,
            close_time TIMESTAMP NOT NULL,
            quote_volume DECIMAL(20, 8),
            count INTEGER,
            taker_buy_volume DECIMAL(18, 8),
            taker_buy_quote_volume DECIMAL(20, 8),
            PRIMARY KEY (open_time, symbol)
        )
    """)
    return table_name


def parquet_glob(catalog: str, data_type: str, symbol: str) -> str:
    """Build glob path for ccxt-data-pipeline Parquet files."""
    return f"{catalog}/{data_type}/{symbol}-PERP.{VENUE}/*.parquet"


def get_watermark(con: duckdb.DuckDBPyConnection, table: str, ts_col: str, symbol: str):
    """Get MAX timestamp for a symbol in a table (the watermark)."""
    result = con.execute(
        f"SELECT MAX({ts_col}) FROM {table} WHERE symbol = ?", [symbol]
    ).fetchone()
    return result[0] if result and result[0] else None


def get_questdb_watermark(
    qdb: QuestDBService, table: str, symbol: str, interval: str | None = None
) -> datetime | None:
    """Get MAX timestamp for a symbol in a QuestDB table."""
    query = f"SELECT max(timestamp) FROM {table} WHERE symbol = %s"
    params = [symbol]
    if interval:
        query += " AND interval = %s"
        params.append(interval)
    rows = qdb.execute_query(query, params)
    return rows[0][0] if rows and rows[0][0] else None


def _fill_klines_interval(
    con: duckdb.DuckDBPyConnection,
    qdb: QuestDBService,
    catalog: str,
    symbol: str,
    interval: str,
    dry_run: bool,
) -> dict:
    """Fill klines gap for a single interval from OHLCV Parquet files to QuestDB."""
    minutes = _kline_minutes(interval)
    glob_path = parquet_glob(catalog, "ohlcv", symbol)

    # Use QuestDB watermark instead of DuckDB
    watermark = get_questdb_watermark(qdb, "klines", symbol, interval)

    bootstrap_days = KLINE_BOOTSTRAP_DAYS_BY_INTERVAL.get(interval)

    if watermark is None and bootstrap_days is None:
        logger.warning(
            "No existing %s klines for %s in QuestDB, skipping (need CSV baseline first)",
            interval,
            symbol,
        )
        return {"inserted": 0, "skipped": "no_baseline"}

    if watermark is None and bootstrap_days is not None:
        # Bootstrap: use a bounded time window instead of requiring CSV baseline
        logger.info(
            "Bootstrapping %s klines for %s with %d-day window",
            interval,
            symbol,
            bootstrap_days,
        )
        ts_filter = f"timestamp > (now() - INTERVAL '{bootstrap_days} days')"
    else:
        logger.info("Klines %s QuestDB watermark for %s: %s", interval, symbol, watermark)
        ts_filter = f"timestamp > TIMESTAMP WITH TIME ZONE '{watermark.isoformat()} UTC'"

    try:
        avail = con.execute(
            f"""
            SELECT COUNT(*) FROM read_parquet('{glob_path}')
            WHERE venue = '{VENUE}'
              AND timeframe = '{interval}'
              AND {ts_filter}
        """
        ).fetchone()[0]
    except Exception as e:
        logger.warning("No Parquet files found for %s klines %s: %s", interval, symbol, e)
        return {"inserted": 0, "skipped": "no_parquet"}

    if avail == 0:
        logger.info("No new %s klines data after watermark", interval)
        return {"inserted": 0, "skipped": "up_to_date"}

    logger.info("Found %d Parquet rows to fill for %s %s klines", avail, symbol, interval)

    if dry_run:
        return {"inserted": 0, "available": avail, "skipped": "dry_run"}

    # Fetch data as dataframe
    df = con.execute(
        f"""
        SELECT
            timezone('UTC', timestamp)::TIMESTAMP AS timestamp,
            REPLACE(symbol, '-PERP', '') AS symbol,
            CAST(open AS DOUBLE) AS open,
            CAST(high AS DOUBLE) AS high,
            CAST(low AS DOUBLE) AS low,
            CAST(close AS DOUBLE) AS close,
            CAST(volume AS DOUBLE) AS volume
        FROM read_parquet('{glob_path}')
        WHERE venue = '{VENUE}'
          AND timeframe = '{interval}'
          AND {ts_filter}
        ORDER BY timestamp ASC
    """
    ).df()

    if not df.empty:
        # Explicitly mark as UTC and pass to QuestDB
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC")
        df["interval"] = interval
        qdb.ingest_dataframe("klines", df, symbol_cols=["symbol", "interval"])
        inserted = len(df)
    else:
        inserted = 0

    logger.info("Klines %s/%s: %d inserted into QuestDB", interval, symbol, inserted)
    return {"inserted": inserted, "duplicates": 0}


def fill_klines(
    con: duckdb.DuckDBPyConnection,
    qdb: QuestDBService,
    catalog: str,
    symbol: str,
    dry_run: bool,
) -> dict:
    """Fill klines gap for all configured intervals (5m, 1m).

    Returns a dict with per-interval results and total inserted count.
    """
    intervals_results: dict[str, dict] = {}
    total_inserted = 0

    for interval in KLINE_INTERVALS:
        result = _fill_klines_interval(con, qdb, catalog, symbol, interval, dry_run)
        intervals_results[interval] = result
        total_inserted += result.get("inserted", 0)

    return {"intervals": intervals_results, "inserted": total_inserted}


def fill_open_interest(
    con: duckdb.DuckDBPyConnection,
    qdb: QuestDBService,
    catalog: str,
    symbol: str,
    dry_run: bool,
) -> dict:
    """Fill open_interest gap from OI Parquet files to QuestDB."""
    glob_path = parquet_glob(catalog, "open_interest", symbol)
    watermark = get_questdb_watermark(qdb, "open_interest", symbol)

    if watermark is None:
        # Bootstrap: use a bounded time window instead of requiring CSV baseline
        logger.info(
            "Bootstrapping OI for %s with %d-day window",
            symbol,
            OI_BOOTSTRAP_DAYS,
        )
        ts_filter = f"timestamp > (now() - INTERVAL '{OI_BOOTSTRAP_DAYS} days')"
    else:
        logger.info("OI QuestDB watermark for %s: %s", symbol, watermark)
        ts_filter = f"timestamp > TIMESTAMP WITH TIME ZONE '{watermark.isoformat()} UTC'"

    try:
        avail = con.execute(
            f"""
            SELECT COUNT(*) FROM read_parquet('{glob_path}')
            WHERE venue = '{VENUE}'
              AND {ts_filter}
        """
        ).fetchone()[0]
    except Exception as e:
        logger.warning("No Parquet files found for OI %s: %s", symbol, e)
        return {"inserted": 0, "skipped": "no_parquet"}

    if avail == 0:
        logger.info("No new OI data after watermark")
        return {"inserted": 0, "skipped": "up_to_date"}

    logger.info("Found %d Parquet rows to fill for %s OI", avail, symbol)

    if dry_run:
        return {"inserted": 0, "available": avail, "skipped": "dry_run"}

    df = con.execute(
        f"""
        SELECT
            timezone('UTC', timestamp)::TIMESTAMP AS timestamp,
            REPLACE(symbol, '-PERP', '') AS symbol,
            CAST(open_interest_value AS DOUBLE) AS open_interest_value
        FROM read_parquet('{glob_path}')
        WHERE venue = '{VENUE}'
          AND {ts_filter}
        ORDER BY timestamp ASC
    """
    ).df()

    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC")
        qdb.ingest_dataframe("open_interest", df, symbol_cols=["symbol"])
        inserted = len(df)
    else:
        inserted = 0

    logger.info("OI %s: %d inserted into QuestDB", symbol, inserted)
    return {"inserted": inserted, "duplicates": 0}


def fill_funding_rate(
    con: duckdb.DuckDBPyConnection,
    qdb: QuestDBService,
    catalog: str,
    symbol: str,
    dry_run: bool,
) -> dict:
    """Fill funding_rate gap from funding rate Parquet files to QuestDB."""
    glob_path = parquet_glob(catalog, "funding_rate", symbol)
    watermark = get_questdb_watermark(qdb, "funding_rates", symbol)

    if watermark is None:
        # Bootstrap: use a bounded time window instead of requiring CSV baseline
        logger.info(
            "Bootstrapping funding rates for %s with %d-day window",
            symbol,
            FUNDING_BOOTSTRAP_DAYS,
        )
        ts_filter = f"timestamp > (now() - INTERVAL '{FUNDING_BOOTSTRAP_DAYS} days')"
    else:
        logger.info("Funding rate QuestDB watermark for %s: %s", symbol, watermark)
        ts_filter = f"timestamp > TIMESTAMP WITH TIME ZONE '{watermark.isoformat()} UTC'"

    try:
        avail = con.execute(
            f"""
            SELECT COUNT(*) FROM read_parquet('{glob_path}')
            WHERE venue = '{VENUE}'
              AND {ts_filter}
        """
        ).fetchone()[0]
    except Exception as e:
        logger.warning("No Parquet files found for funding rate %s: %s", symbol, e)
        return {"inserted": 0, "skipped": "no_parquet"}

    if avail == 0:
        logger.info("No new funding rate data after watermark")
        return {"inserted": 0, "skipped": "up_to_date"}

    logger.info("Found %d Parquet rows to fill for %s funding rate", avail, symbol)

    if dry_run:
        return {"inserted": 0, "available": avail, "skipped": "dry_run"}

    df = con.execute(
        f"""
        SELECT
            timezone('UTC', timestamp)::TIMESTAMP AS timestamp,
            REPLACE(symbol, '-PERP', '') AS symbol,
            CAST(funding_rate AS DOUBLE) AS funding_rate
        FROM read_parquet('{glob_path}')
        WHERE venue = '{VENUE}'
          AND {ts_filter}
        ORDER BY timestamp ASC
    """
    ).df()

    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC")
        qdb.ingest_dataframe("funding_rates", df, symbol_cols=["symbol"])
        inserted = len(df)
    else:
        inserted = 0

    logger.info("Funding rate %s: %d inserted into QuestDB", symbol, inserted)
    return {"inserted": inserted, "duplicates": 0}


def validate_gaps(qdb: QuestDBService, symbol: str, watermark_ts: datetime | None):
    """Check for gaps in QuestDB klines (5m) after the original watermark."""
    if watermark_ts is None:
        return

    # QuestDB query for gaps
    # timestamp subtraction in QuestDB returns microseconds. 
    # 300s * 1.5 = 450s = 450,000,000 micros.
    query = """
        SELECT count(*) FROM (
            SELECT timestamp,
                   lead(timestamp) OVER (ORDER BY timestamp) as next_ts
            FROM klines
            WHERE symbol = %s AND interval = '5m' AND timestamp >= %s
        ) WHERE next_ts - timestamp > 450000000
    """
    rows = qdb.execute_query(query, [symbol, watermark_ts])
    result = rows[0][0] if rows else 0

    if result > 0:
        logger.warning(
            "Gap validation: %d gaps in QuestDB klines %s after %s",
            result,
            symbol,
            watermark_ts,
        )
    else:
        logger.info("Gap validation: no gaps in QuestDB klines %s after %s", symbol, watermark_ts)


def run_gap_fill(
    db_path: str | Path,
    catalog: str | Path,
    symbols: list[str],
    dry_run: bool = False,
) -> dict:
    """Run the full gap-fill pipeline for all symbols.

    Uses DuckDB only as an in-process Parquet query engine, fills klines/OI/funding
    directly into QuestDB for each symbol, validates gaps, and returns a summary dict.

    Args:
        db_path: Historical DuckDB path. Kept for backward compatibility and
            ignored when missing because raw hot history is no longer persisted there.
        catalog: Path to the ccxt-data-pipeline Parquet catalog.
        symbols: List of symbols to process (e.g. ["BTCUSDT", "ETHUSDT"]).
        dry_run: If True, count available data without writing to QuestDB.

    Returns:
        Dict with per-symbol results and total_inserted count.
    """
    catalog_path = Path(catalog)
    if not catalog_path.is_dir():
        raise FileNotFoundError(f"CCXT catalog not found: {catalog_path}")

    db = Path(db_path)
    logger.info("Gap fill: catalog=%s db=%s symbols=%s dry_run=%s", catalog, db, symbols, dry_run)

    qdb = QuestDBService()
    if qdb._sender is None and not dry_run:
        logger.error("QuestDB Sender not available, cannot run gap fill")
        return {"symbols": {}, "total_inserted": 0, "error": "questdb_unavailable"}

    if db.exists():
        con = duckdb.connect(str(db), read_only=True)
    else:
        logger.info(
            "Gap fill: historical DuckDB %s not found, using in-memory DuckDB for Parquet reads",
            db,
        )
        con = duckdb.connect(":memory:")
    # Cap DuckDB memory to avoid OOM.
    con.execute("SET memory_limit='1GB'")
    summary: dict[str, dict] = {}

    try:
        for symbol in symbols:
            logger.info("=== Processing %s ===", symbol)
            symbol_results = {}

            # Get pre-ingestion watermark for validation
            klines_watermark = get_questdb_watermark(qdb, "klines", symbol, "5m")

            symbol_results["klines"] = fill_klines(con, qdb, str(catalog_path), symbol, dry_run)
            time.sleep(0.1)

            symbol_results["oi"] = fill_open_interest(con, qdb, str(catalog_path), symbol, dry_run)
            time.sleep(0.1)

            symbol_results["funding"] = fill_funding_rate(con, qdb, str(catalog_path), symbol, dry_run)
            time.sleep(0.1)

            if not dry_run:
                validate_gaps(qdb, symbol, klines_watermark)

            summary[symbol] = symbol_results
    finally:
        con.close()

    total_inserted = sum(
        r.get("inserted", 0)
        for sym_results in summary.values()
        for r in sym_results.values()
    )
    logger.info("Gap fill complete: %d total rows inserted into QuestDB", total_inserted)

    return {"symbols": summary, "total_inserted": total_inserted}
