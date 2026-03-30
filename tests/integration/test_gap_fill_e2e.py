"""End-to-end tests for run_gap_fill() with a Parquet catalog and fake QuestDB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.liquidationheatmap.ingestion.gap_fill import run_gap_fill


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class _FakeQuestDB:
    def __init__(self, base_ts: datetime, empty: bool = False):
        self._sender = object()
        if empty:
            self.tables = {
                "klines": pd.DataFrame(),
                "open_interest": pd.DataFrame(),
                "funding_rates": pd.DataFrame(),
            }
        else:
            self.tables = {
                "klines": pd.DataFrame(
                    [
                        {
                            "timestamp": (base_ts - timedelta(minutes=5)).replace(tzinfo=None),
                            "symbol": "BTCUSDT",
                            "interval": "5m",
                            "open": 89900.0,
                            "high": 90000.0,
                            "low": 89800.0,
                            "close": 89950.0,
                            "volume": 50.0,
                        }
                    ]
                ),
                "open_interest": pd.DataFrame(
                    [
                        {
                            "timestamp": (base_ts - timedelta(minutes=4)).replace(tzinfo=None),
                            "symbol": "BTCUSDT",
                            "open_interest_value": 7.1e9,
                        }
                    ]
                ),
                "funding_rates": pd.DataFrame(
                    [
                        {
                            "timestamp": (base_ts - timedelta(hours=8)).replace(tzinfo=None),
                            "symbol": "BTCUSDT",
                            "funding_rate": 0.00008,
                        }
                    ]
                ),
            }

    def execute_query(self, query, params=None):
        params = params or []
        lowered = " ".join(query.lower().split())

        if "lead(timestamp)" in lowered:
            return [(0,)]

        if "select max(timestamp)" in lowered:
            if "from klines" in lowered:
                table = self.tables["klines"]
                if table.empty:
                    return [(None,)]
                symbol = params[0]
                interval = params[1] if len(params) > 1 else None
                filtered = table[table["symbol"] == symbol]
                if interval is not None:
                    filtered = filtered[filtered["interval"] == interval]
            elif "from open_interest" in lowered:
                table = self.tables["open_interest"]
                if table.empty:
                    return [(None,)]
                filtered = table[table["symbol"] == params[0]]
            elif "from funding_rates" in lowered:
                table = self.tables["funding_rates"]
                if table.empty:
                    return [(None,)]
                filtered = table[table["symbol"] == params[0]]
            else:
                filtered = pd.DataFrame()

            if filtered.empty:
                return [(None,)]
            return [(filtered["timestamp"].max().to_pydatetime(),)]

        return []

    def ingest_dataframe(self, table_name, df, symbol_cols=None, timestamp_col="timestamp"):
        existing = self.tables.get(table_name)
        incoming = df.copy()
        # Drop tz if present for pandas comparison in fake
        if "timestamp" in incoming.columns:
            incoming["timestamp"] = pd.to_datetime(incoming["timestamp"]).dt.tz_localize(None)

        if existing is None or existing.empty:
            self.tables[table_name] = incoming
            return

        combined = pd.concat([existing, incoming], ignore_index=True)
        subset = [timestamp_col, *(symbol_cols or [])]
        self.tables[table_name] = combined.drop_duplicates(subset=subset, keep="first")


@pytest.fixture
def e2e_catalog(tmp_path):
    """Create a complete ccxt-data-pipeline catalog with 5m, 1m, OI, funding."""
    catalog = tmp_path / "catalog"
    base_ts = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(days=1)

    ohlcv_dir = catalog / "ohlcv" / "BTCUSDT-PERP.BINANCE"
    ohlcv_dir.mkdir(parents=True)

    ohlcv_5m = pa.table(
        {
            "timestamp": pa.array(
                [
                    base_ts,
                    base_ts + timedelta(minutes=5),
                ],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "symbol": ["BTCUSDT-PERP"] * 2,
            "venue": ["BINANCE"] * 2,
            "timeframe": ["5m"] * 2,
            "open": [90000.0, 90100.0],
            "high": [90200.0, 90150.0],
            "low": [89900.0, 90000.0],
            "close": [90100.0, 90050.0],
            "volume": [100.5, 200.3],
        }
    )

    ohlcv_1m = pa.table(
        {
            "timestamp": pa.array(
                [
                    base_ts,
                    base_ts + timedelta(minutes=1),
                    base_ts + timedelta(minutes=2),
                ],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "symbol": ["BTCUSDT-PERP"] * 3,
            "venue": ["BINANCE"] * 3,
            "timeframe": ["1m"] * 3,
            "open": [90000.0, 90010.0, 90020.0],
            "high": [90050.0, 90060.0, 90070.0],
            "low": [89990.0, 90000.0, 90010.0],
            "close": [90010.0, 90020.0, 90030.0],
            "volume": [10.1, 12.3, 11.5],
        }
    )

    pq.write_table(
        pa.concat_tables([ohlcv_5m, ohlcv_1m]),
        ohlcv_dir / f"{base_ts.date().isoformat()}.parquet",
    )

    oi_dir = catalog / "open_interest" / "BTCUSDT-PERP.BINANCE"
    oi_dir.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "timestamp": pa.array(
                [
                    base_ts + timedelta(minutes=1),
                    base_ts + timedelta(minutes=6),
                ],
                type=pa.timestamp("us", tz="UTC"),
            ),
                "symbol": ["BTCUSDT-PERP"] * 2,
                "venue": ["BINANCE"] * 2,
                "open_interest": [80000.0, 80100.0],
                "open_interest_value": [7.2e9, 7.3e9],
            }
        ),
        oi_dir / f"{base_ts.date().isoformat()}.parquet",
    )

    fr_dir = catalog / "funding_rate" / "BTCUSDT-PERP.BINANCE"
    fr_dir.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "timestamp": pa.array([base_ts], type=pa.timestamp("us", tz="UTC")),
                "symbol": ["BTCUSDT-PERP"],
                "venue": ["BINANCE"],
                "funding_rate": [0.00015],
                "next_funding_time": pa.array(
                    [base_ts + timedelta(hours=8)], type=pa.timestamp("us", tz="UTC")
                ),
                "predicted_rate": pa.array([None], type=pa.float64()),
            }
        ),
        fr_dir / f"{base_ts.date().isoformat()}.parquet",
    )

    return str(catalog), base_ts


@pytest.fixture
def missing_db_path(tmp_path):
    """Gap fill no longer requires a historical DuckDB file to exist."""
    return str(tmp_path / "missing-historical.duckdb")


class TestGapFillE2E:
    def test_full_pipeline(self, missing_db_path, e2e_catalog, monkeypatch):
        catalog_path, base_ts = e2e_catalog
        fake_qdb = _FakeQuestDB(base_ts)
        monkeypatch.setattr("src.liquidationheatmap.ingestion.gap_fill.QuestDBService", lambda: fake_qdb)

        result = run_gap_fill(
            db_path=missing_db_path,
            catalog=catalog_path,
            symbols=["BTCUSDT"],
            dry_run=False,
        )

        assert result["total_inserted"] == 8
        btc = result["symbols"]["BTCUSDT"]
        assert btc["klines"]["intervals"]["5m"]["inserted"] == 2
        assert btc["klines"]["intervals"]["1m"]["inserted"] == 3
        assert btc["oi"]["inserted"] == 2
        assert btc["funding"]["inserted"] == 1

        assert len(fake_qdb.tables["klines"]) == 6
        assert len(fake_qdb.tables["open_interest"]) == 3
        assert len(fake_qdb.tables["funding_rates"]) == 2

    def test_freshness(self, missing_db_path, e2e_catalog, monkeypatch):
        catalog_path, base_ts = e2e_catalog
        fake_qdb = _FakeQuestDB(base_ts)
        monkeypatch.setattr("src.liquidationheatmap.ingestion.gap_fill.QuestDBService", lambda: fake_qdb)

        run_gap_fill(
            db_path=missing_db_path,
            catalog=catalog_path,
            symbols=["BTCUSDT"],
            dry_run=False,
        )

        max_5m = fake_qdb.tables["klines"].query("symbol == 'BTCUSDT' and interval == '5m'")[
            "timestamp"
        ].max()
        max_oi = fake_qdb.tables["open_interest"].query("symbol == 'BTCUSDT'")["timestamp"].max()
        max_fr = fake_qdb.tables["funding_rates"].query("symbol == 'BTCUSDT'")["timestamp"].max()

        assert max_5m.to_pydatetime() == (base_ts + timedelta(minutes=5)).replace(tzinfo=None)
        assert max_oi.to_pydatetime() == (base_ts + timedelta(minutes=6)).replace(tzinfo=None)
        assert max_fr.to_pydatetime() == base_ts.replace(tzinfo=None)

    def test_idempotent(self, missing_db_path, e2e_catalog, monkeypatch):
        catalog_path, base_ts = e2e_catalog
        fake_qdb = _FakeQuestDB(base_ts)
        monkeypatch.setattr("src.liquidationheatmap.ingestion.gap_fill.QuestDBService", lambda: fake_qdb)

        r1 = run_gap_fill(missing_db_path, catalog_path, ["BTCUSDT"], dry_run=False)
        r2 = run_gap_fill(missing_db_path, catalog_path, ["BTCUSDT"], dry_run=False)

        assert r1["total_inserted"] == 8
        assert r2["total_inserted"] == 0

    def test_bootstrap_empty_qdb(self, missing_db_path, e2e_catalog, monkeypatch):
        catalog_path, base_ts = e2e_catalog
        fake_qdb = _FakeQuestDB(base_ts, empty=True)
        monkeypatch.setattr("src.liquidationheatmap.ingestion.gap_fill.QuestDBService", lambda: fake_qdb)

        result = run_gap_fill(
            db_path=missing_db_path,
            catalog=catalog_path,
            symbols=["BTCUSDT"],
            dry_run=False,
        )

        # Should bootstrap all types because they now all have bootstrap windows
        assert result["total_inserted"] == 8
        btc = result["symbols"]["BTCUSDT"]
        assert btc["klines"]["intervals"]["5m"]["inserted"] == 2
        assert btc["klines"]["intervals"]["1m"]["inserted"] == 3
        assert btc["oi"]["inserted"] == 2
        assert btc["funding"]["inserted"] == 1

        assert len(fake_qdb.tables["klines"]) == 5
        assert len(fake_qdb.tables["open_interest"]) == 2
        assert len(fake_qdb.tables["funding_rates"]) == 1
