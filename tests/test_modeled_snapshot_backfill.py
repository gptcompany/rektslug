import pytest
import json
from datetime import datetime, timezone, timedelta
from src.liquidationheatmap.modeled_snapshots.binance_producer import BinanceProducer
from src.liquidationheatmap.modeled_snapshots.backfill import BackfillCoordinator

@pytest.fixture
def mock_db_backfill(tmp_path):
    import duckdb
    db_file = tmp_path / "backfill.db"
    conn = duckdb.connect(str(db_file))
    conn.execute("CREATE TABLE klines_1m_history (symbol VARCHAR, open_time TIMESTAMP, close DOUBLE)")
    conn.execute("CREATE TABLE open_interest_history (symbol VARCHAR, timestamp TIMESTAMP, open_interest_value DOUBLE)")
    conn.execute("""
        CREATE TABLE aggtrades_history (
            agg_trade_id BIGINT, 
            timestamp TIMESTAMP, 
            symbol VARCHAR, 
            exchange VARCHAR, 
            price DOUBLE, 
            quantity DOUBLE, 
            side VARCHAR, 
            gross_value DOUBLE
        )
    """)
    
    # Insert data for 3 hours
    for i in range(4):
        ts = datetime(2026, 4, 7, 12 + i, 0, 0, tzinfo=timezone.utc)
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO klines_1m_history VALUES ('BTCUSDT', ?, 50000.0)", [ts_str])
        conn.execute("INSERT INTO open_interest_history VALUES ('BTCUSDT', ?, 10000.0)", [ts_str])
        
    conn.close()
    return str(db_file)

def test_backfill_determinism(tmp_path, mock_db_backfill, monkeypatch):
    producer = BinanceProducer(base_dir=tmp_path, db_path=mock_db_backfill)
    # Mock orderbook to ensure consistency
    def mock_ob(symbol, ts):
        return {'bids': [(49500.0, 1.0)], 'asks': [(50500.0, 1.0)]}, {"source": "mock"}, "available"
    monkeypatch.setattr(producer, "_collect_orderbook", mock_ob)
    
    coordinator = BackfillCoordinator(producer)
    
    start_ts = "2026-04-07T12:00:00Z"
    end_ts = "2026-04-07T14:00:00Z"
    
    # Run 1
    record1 = coordinator.run_backfill("binance", "BTCUSDT", start_ts, end_ts, step_minutes=60, batch_id="batch1")

    # Check that artifact contents are identical (except generation metadata)
    snapshot_ts = "2026-04-07T12:00:00Z"
    artifact_path = tmp_path / "artifacts" / "BTCUSDT" / snapshot_ts / "binance_standard.json"
    
    with open(artifact_path, "r") as f:
        data1 = json.load(f)

    # Run 2
    record2 = coordinator.run_backfill("binance", "BTCUSDT", start_ts, end_ts, step_minutes=60, batch_id="batch2")

    with open(artifact_path, "r") as f:
        data2 = json.load(f)
        
    # Remove generation metadata which is allowed to differ
    data1.pop("generation_metadata")
    data2.pop("generation_metadata")
    
    assert data1 == data2
    assert record1.coverage == record2.coverage
