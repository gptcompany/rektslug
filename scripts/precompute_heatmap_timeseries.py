#!/usr/bin/env python3
"""Pre-compute heatmap timeseries snapshots into DuckDB cache.

Runs incrementally: only computes snapshots for timestamps not already cached.
Intended to run post-gap-fill in the ingestion cron cycle.

Usage:
    uv run scripts/precompute_heatmap_timeseries.py --symbol BTCUSDT --interval 15m --days 7
    uv run scripts/precompute_heatmap_timeseries.py --all  # BTC+ETH at 15m+1h
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

INGESTION_LOCK_FILE = Path("/tmp/duckdb-ingestion.lock")

# Default configs for pre-computation
DEFAULT_CONFIGS = [
    {"symbol": "BTCUSDT", "interval": "15m", "days": 30, "price_bin_size": 100.0},
    {"symbol": "BTCUSDT", "interval": "1h", "days": 90, "price_bin_size": 100.0},
    {"symbol": "ETHUSDT", "interval": "15m", "days": 30, "price_bin_size": 10.0},
    {"symbol": "ETHUSDT", "interval": "1h", "days": 90, "price_bin_size": 10.0},
]


def check_ingestion_lock() -> bool:
    """Check if ingestion lock is held. Returns True if locked."""
    if INGESTION_LOCK_FILE.exists():
        try:
            age = time.time() - INGESTION_LOCK_FILE.stat().st_mtime
            if age < 600:  # 10 min max age
                return True
            logger.warning(f"Stale lock file (age={age:.0f}s), ignoring")
        except OSError:
            pass
    return False


def precompute_single(
    symbol: str,
    interval: str,
    days: int,
    price_bin_size: float,
) -> int:
    """Pre-compute missing heatmap timeseries snapshots for one config.

    Returns number of snapshots inserted.
    """
    from src.liquidationheatmap.ingestion.db_service import DuckDBService

    # Phase 1: Find what's missing
    with DuckDBService(read_only=True) as db_ro:
        db_ro.ensure_heatmap_ts_cache_table()
        last_cached = db_ro.get_last_cached_ts_timestamp(symbol, interval)

    now = datetime.now(timezone.utc)
    if last_cached:
        start = datetime.fromisoformat(str(last_cached).replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        # Start from next interval after last cached
        interval_map = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1)}
        start = start + interval_map.get(interval, timedelta(minutes=15))
    else:
        start = now - timedelta(days=days)

    if start >= now:
        logger.info(f"[{symbol}/{interval}] Cache is up to date, nothing to compute")
        return 0

    # Phase 2: Compute missing snapshots
    start_str = start.strftime("%Y-%m-%d %H:%M:%S")
    end_str = now.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{symbol}/{interval}] Computing snapshots from {start_str} to {end_str}")

    with DuckDBService(read_only=True) as db_ro:
        snapshots = db_ro.get_heatmap_timeseries(
            symbol=symbol,
            start_time=start_str,
            end_time=end_str,
            interval=interval,
            price_bin_size=price_bin_size,
        )

    if not snapshots:
        logger.info(f"[{symbol}/{interval}] No snapshots computed (no data in range)")
        return 0

    # Phase 3: Serialize and batch insert
    rows = []
    for s in snapshots:
        payload = json.dumps(s.to_dict(), default=str)
        ts_str = (
            s.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(s.timestamp, "strftime")
            else str(s.timestamp)
        )
        rows.append((symbol, interval, ts_str, price_bin_size, payload))

    if check_ingestion_lock():
        logger.warning(f"[{symbol}/{interval}] Ingestion lock held, skipping cache write")
        return 0

    DuckDBService.reset_singletons()
    with DuckDBService(read_only=False) as db_rw:
        db_rw.conn.execute("SET memory_limit='1GB'")
        db_rw.ensure_heatmap_ts_cache_table()
        inserted = db_rw.put_cached_ts_snapshots(rows)
        db_rw.delete_stale_ts_cache()
    DuckDBService.reset_singletons()

    logger.info(f"[{symbol}/{interval}] Inserted {inserted} snapshots into cache")
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Pre-compute heatmap timeseries cache")
    parser.add_argument("--symbol", type=str, help="Trading pair (e.g. BTCUSDT)")
    parser.add_argument("--interval", type=str, choices=["15m", "1h"], help="Interval")
    parser.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    parser.add_argument("--price-bin-size", type=float, default=100.0, help="Price bin size")
    parser.add_argument(
        "--all", action="store_true", help="Run all default configs (BTC+ETH, 15m+1h)"
    )
    args = parser.parse_args()

    if check_ingestion_lock():
        logger.warning("Ingestion lock held, exiting")
        sys.exit(0)

    start_time = time.time()
    total_inserted = 0

    if args.all:
        configs = DEFAULT_CONFIGS
    elif args.symbol and args.interval:
        configs = [
            {
                "symbol": args.symbol,
                "interval": args.interval,
                "days": args.days,
                "price_bin_size": args.price_bin_size,
            }
        ]
    else:
        parser.error("Either --all or --symbol + --interval required")
        return

    for cfg in configs:
        try:
            inserted = precompute_single(**cfg)
            total_inserted += inserted
        except Exception as e:
            logger.error(f"[{cfg['symbol']}/{cfg['interval']}] Failed: {e}", exc_info=True)

    duration = time.time() - start_time
    logger.info(f"Pre-computation complete: {total_inserted} total snapshots in {duration:.1f}s")


if __name__ == "__main__":
    main()
