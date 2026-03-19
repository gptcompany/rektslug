from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.liquidationheatmap.ingestion.db_service import DuckDBService


@pytest.fixture
def heatmap_db(tmp_path):
    db_path = str(tmp_path / "heatmap_timeseries.duckdb")
    service = DuckDBService(db_path)

    for interval in ("1m", "5m", "15m"):
        service.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS klines_{interval}_history (
                open_time TIMESTAMP NOT NULL,
                symbol VARCHAR NOT NULL,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                quote_volume DOUBLE,
                PRIMARY KEY (open_time, symbol)
            )
            """
        )

    service.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS open_interest_history (
            id BIGINT PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR NOT NULL,
            open_interest_value DOUBLE NOT NULL,
            open_interest_contracts DOUBLE NOT NULL,
            source VARCHAR DEFAULT 'ccxt'
        )
        """
    )

    yield service
    service.close()


def _insert_candle(
    service: DuckDBService,
    table_name: str,
    timestamp: datetime,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 10.0,
):
    service.conn.execute(
        f"""
        INSERT INTO {table_name}
        (open_time, symbol, open, high, low, close, volume, quote_volume)
        VALUES (?, 'BTCUSDT', ?, ?, ?, ?, ?, ?)
        """,
        [timestamp, open_price, high_price, low_price, close_price, volume, close_price * volume],
    )


def _insert_oi(service: DuckDBService, row_id: int, timestamp: datetime, value: float):
    service.conn.execute(
        """
        INSERT INTO open_interest_history
        (id, timestamp, symbol, open_interest_value, open_interest_contracts, source)
        VALUES (?, ?, 'BTCUSDT', ?, 1.0, 'ccxt')
        """,
        [row_id, timestamp, value],
    )


def test_get_heatmap_timeseries_resamples_snapshots_to_requested_interval(heatmap_db):
    base = datetime(2026, 3, 11, 10, 0, 0)

    for offset_minutes, close_price in ((0, 101.0), (15, 102.0), (30, 103.0), (45, 104.0)):
        timestamp = base + timedelta(minutes=offset_minutes)
        _insert_candle(
            heatmap_db,
            "klines_15m_history",
            timestamp,
            open_price=100.0 + (offset_minutes / 15),
            high_price=105.0,
            low_price=99.0,
            close_price=close_price,
        )

    _insert_oi(heatmap_db, 1, base - timedelta(minutes=15), 900.0)
    _insert_oi(heatmap_db, 2, base, 1000.0)
    _insert_oi(heatmap_db, 3, base + timedelta(minutes=15), 1100.0)
    _insert_oi(heatmap_db, 4, base + timedelta(minutes=30), 1200.0)
    _insert_oi(heatmap_db, 5, base + timedelta(minutes=45), 1300.0)

    with patch.object(
        heatmap_db,
        "_resolve_oi_kline_source",
        return_value=("klines_15m_history", "15m"),
    ):
        snapshots = heatmap_db.get_heatmap_timeseries(
            symbol="BTCUSDT",
            start_time=base.isoformat(),
            end_time=(base + timedelta(minutes=45)).isoformat(),
            interval="1h",
            price_bin_size=100.0,
        )

    assert len(snapshots) == 1
    assert snapshots[0].timestamp == base
    assert snapshots[0].positions_created > 0


def test_get_heatmap_timeseries_assigns_each_oi_delta_to_one_candle(heatmap_db):
    base = datetime(2026, 3, 11, 10, 0, 0)

    for offset_minutes in range(5):
        timestamp = base + timedelta(minutes=offset_minutes)
        _insert_candle(
            heatmap_db,
            "klines_1m_history",
            timestamp,
            open_price=100.0,
            high_price=102.0,
            low_price=99.0,
            close_price=101.0,
        )

    _insert_oi(heatmap_db, 1, base - timedelta(minutes=1), 1000.0)
    _insert_oi(heatmap_db, 2, base + timedelta(minutes=2), 1300.0)

    with patch.object(
        heatmap_db,
        "_resolve_oi_kline_source",
        return_value=("klines_1m_history", "1m"),
    ):
        snapshots = heatmap_db.get_heatmap_timeseries(
            symbol="BTCUSDT",
            start_time=base.isoformat(),
            end_time=(base + timedelta(minutes=4)).isoformat(),
            interval="1m",
            price_bin_size=100.0,
        )

    created_counts = [snapshot.positions_created for snapshot in snapshots]

    assert len(snapshots) == 5
    assert created_counts[2] > 0
    assert sum(1 for count in created_counts if count > 0) == 1


def test_resolve_oi_kline_source_ignores_stale_1m_tables(heatmap_db):
    now = datetime.now().replace(second=0, microsecond=0)

    stale_end = now - timedelta(hours=12)
    for i in range(1000):
        _insert_candle(
            heatmap_db,
            "klines_1m_history",
            stale_end - timedelta(minutes=i),
            open_price=100.0,
            high_price=101.0,
            low_price=99.0,
            close_price=100.5,
            volume=1.0,
        )

    for i in range(200):
        _insert_candle(
            heatmap_db,
            "klines_5m_history",
            now - timedelta(minutes=5 * i),
            open_price=100.0,
            high_price=101.0,
            low_price=99.0,
            close_price=100.5,
            volume=1.0,
        )

    table_name, interval = heatmap_db._resolve_oi_kline_source(
        "BTCUSDT",
        lookback_days=1,
        kline_interval="auto",
    )

    assert table_name == "klines_5m_history"
    assert interval == "5m"
