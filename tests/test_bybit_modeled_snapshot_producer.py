import pytest
import json
import duckdb
from pathlib import Path
from src.liquidationheatmap.modeled_snapshots.bybit_producer import BybitProducer

def test_bybit_blocked_manifest_gap(tmp_path):
    producer = BybitProducer(base_dir=tmp_path)
    # Gap is 2025-08-21 to 2026-04-05
    gap_ts = "2025-12-01T12:00:00Z"
    
    manifest = producer.export_snapshot(symbol="BTCUSDT", snapshot_ts=gap_ts, channels=["depth_weighted"])
    
    assert manifest.exchange == "bybit"
    assert manifest.models["depth_weighted"].availability_status == "blocked_source_missing"
    
    # Check that NO artifact was written
    artifact_dir = tmp_path / "bybit" / "artifacts" / "BTCUSDT" / gap_ts
    assert not artifact_dir.exists()
    
    # Check that manifest was written
    manifest_path = tmp_path / "bybit" / "manifests" / "BTCUSDT" / f"{gap_ts}.json"
    assert manifest_path.exists()
    
    with open(manifest_path, "r") as f:
        data = json.load(f)
    assert data["models"]["depth_weighted"]["availability_status"] == "blocked_source_missing"

def test_bybit_export_available_mock(tmp_path, monkeypatch):
    # Mocking paths and DB to test successful export
    producer = BybitProducer(base_dir=tmp_path)
    snapshot_ts = "2026-04-07T12:00:00Z"
    
    from src.liquidationheatmap.modeled_snapshots.bybit_readiness import ReadinessReport
    def mock_check_readiness(symbol, ts, channel):
        return ReadinessReport("bybit", ts, channel, "available", {})
        
    def mock_collect_inputs(symbol, ts, lookback, channel, report=None):
        import pandas as pd
        from decimal import Decimal
        inputs = {
            "current_price": Decimal("50000.0"),
            "open_interest": Decimal("1000000.0"),
            "large_trades": pd.DataFrame(),
            "orderbook": {'bids': [(49500.0, 1.0)], 'asks': [(50500.0, 1.0)]}
        }
        return inputs, {"mock": True}, "available"
        
    monkeypatch.setattr(producer.readiness_gate, "check_readiness", mock_check_readiness)
    monkeypatch.setattr(producer, "_collect_inputs", mock_collect_inputs)
    
    manifest = producer.export_snapshot(symbol="BTCUSDT", snapshot_ts=snapshot_ts)
    assert manifest.models["bybit_standard"].availability_status == "available"
    assert (tmp_path / "bybit" / "artifacts" / "BTCUSDT" / snapshot_ts / "bybit_standard.json").exists()


def test_bybit_partial_manifest_keeps_artifact_path(tmp_path, monkeypatch):
    producer = BybitProducer(base_dir=tmp_path)
    snapshot_ts = "2026-04-07T12:00:00Z"

    from src.liquidationheatmap.modeled_snapshots.bybit_readiness import ReadinessReport

    def mock_check_readiness(symbol, ts, channel):
        return ReadinessReport("bybit", ts, channel, "available", {})

    def mock_collect_inputs(symbol, ts, lookback, channel, report=None):
        import pandas as pd
        from decimal import Decimal

        inputs = {
            "current_price": Decimal("50000.0"),
            "open_interest": Decimal("1000000.0"),
            "large_trades": pd.DataFrame(),
        }
        input_identity = {
            "current_price": {"source": "mock", "timestamp": ts},
            "open_interest": {"source": "mock", "timestamp": ts},
            "funding": {"source": "missing", "status": "missing"},
            "large_trades": {"source": "mock", "count": 0},
        }
        return inputs, input_identity, "partial"

    monkeypatch.setattr(producer.readiness_gate, "check_readiness", mock_check_readiness)
    monkeypatch.setattr(producer, "_collect_inputs", mock_collect_inputs)

    manifest = producer.export_snapshot(
        symbol="BTCUSDT", snapshot_ts=snapshot_ts, channels=["bybit_standard"]
    )

    entry = manifest.models["bybit_standard"]
    assert entry.availability_status == "partial"
    assert entry.artifact_path == f"artifacts/BTCUSDT/{snapshot_ts}/bybit_standard.json"
    assert entry.source_metadata["availability_metadata"]["reason"] == "Input collection was partial"


def test_bybit_normalized_historical_export(tmp_path):
    import pandas as pd
    from decimal import Decimal
    from src.liquidationheatmap.modeled_snapshots.bybit_readiness import BybitReadinessGate

    # 1. Setup readiness gate with normalized paths
    gate = BybitReadinessGate(
        catalog_root=tmp_path / "catalog",
        historical_root=tmp_path / "historical",
        metrics_root=tmp_path / "metrics",
        normalized_root=tmp_path / "normalized",
    )
    producer = BybitProducer(base_dir=tmp_path)
    producer.readiness_gate = gate
    
    date_str = "2024-01-01"
    snapshot_ts = "2024-01-01T12:00:00Z"
    
    # 2. Create mock Parquet files in normalized historical paths
    for input_type in ["klines", "open_interest", "funding", "trades", "orderbook"]:
        normalized_path = tmp_path / "normalized" / input_type / "BTCUSDT-PERP.BYBIT" / f"{date_str}.parquet"
        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        
        if input_type == "klines":
            df = pd.DataFrame({"timestamp": ["2024-01-01T11:59:00Z"], "close": [40000.0]})
        elif input_type == "open_interest":
            df = pd.DataFrame({"timestamp": ["2024-01-01T11:59:00Z"], "open_interest_value": [5000.0]})
        elif input_type == "funding":
            df = pd.DataFrame({"timestamp": ["2024-01-01T11:59:00Z"], "funding_rate": [0.0001], "next_funding_time": ["2024-01-01T16:00:00Z"], "predicted_rate": [0.0001]})
        elif input_type == "trades":
            df = pd.DataFrame({"timestamp": ["2024-01-01T11:59:00Z"], "price": [40000.0], "quantity": [2.0], "side": ["buy"], "value": [80000.0]})
        elif input_type == "orderbook":
            cols = {"timestamp": ["2024-01-01T11:59:00Z"], "receipt_timestamp": ["2024-01-01T11:59:00Z"], "exchange": ["bybit"], "symbol": ["BTCUSDT"]}
            for i in range(20):
                cols[f"bid_{i}_price"] = [39000.0 - i*10]
                cols[f"bid_{i}_size"] = [1.0]
                cols[f"ask_{i}_price"] = [41000.0 + i*10]
                cols[f"ask_{i}_size"] = [1.0]
            df = pd.DataFrame(cols)
        
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if "next_funding_time" in df.columns:
            df["next_funding_time"] = pd.to_datetime(df["next_funding_time"])
        if "receipt_timestamp" in df.columns:
            df["receipt_timestamp"] = pd.to_datetime(df["receipt_timestamp"])
            
        df.to_parquet(normalized_path)
    
    # 3. Export
    manifest = producer.export_snapshot(
        symbol="BTCUSDT", snapshot_ts=snapshot_ts, channels=["bybit_standard", "depth_weighted"]
    )
    
    # 4. Assert success and artifact presence
    assert manifest.models["bybit_standard"].availability_status == "available"
    assert manifest.models["depth_weighted"].availability_status == "available"
    assert (tmp_path / "bybit" / "artifacts" / "BTCUSDT" / snapshot_ts / "bybit_standard.json").exists()


def test_bybit_bridge_normalized_export(tmp_path):
    import gzip
    import json
    import zipfile

    from src.liquidationheatmap.modeled_snapshots.bybit_historical_bridge import BybitHistoricalBridge
    from src.liquidationheatmap.modeled_snapshots.bybit_readiness import BybitReadinessGate

    historical_root = tmp_path / "historical"
    metrics_root = tmp_path / "metrics"
    normalized_root = tmp_path / "normalized"

    bridge = BybitHistoricalBridge(
        historical_root=historical_root,
        normalized_root=normalized_root,
        metrics_root=metrics_root,
    )

    symbol = "BTCUSDT"
    date_str = "2024-01-01"
    snapshot_ts = "2024-01-01T12:00:00Z"

    kline_path = bridge.resolve_raw_path(symbol, date_str, "klines")
    kline_path.parent.mkdir(parents=True, exist_ok=True)
    kline_path.write_text('[[1704110340000, "40000.0", "40100.0", "39900.0", "40050.0", "1.5", "60000.0"]]')

    trade_path = bridge.resolve_raw_path(symbol, date_str, "trades")
    trade_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(trade_path, "wt") as f:
        f.write("timestamp,price,quantity,side\n1704110340000,40000.0,20.0,buy\n")

    funding_path = bridge.resolve_raw_path(symbol, date_str, "funding")
    funding_path.parent.mkdir(parents=True, exist_ok=True)
    funding_path.write_text(json.dumps([{"funding_rate": "0.0001", "funding_rate_timestamp": 1704110340000}]))

    oi_path = bridge.resolve_raw_path(symbol, date_str, "open_interest")
    oi_path.parent.mkdir(parents=True, exist_ok=True)
    oi_path.write_text(json.dumps([{"open_interest": "50000.5", "timestamp": 1704110340000}]))

    orderbook_path = bridge.resolve_raw_path(symbol, date_str, "orderbook")
    orderbook_path.parent.mkdir(parents=True, exist_ok=True)
    csv_content = (
        "timestamp,side,price,size,symbol\n"
        "1704110340000,Buy,40000.0,1.5,BTCUSDT\n"
        "1704110340000,Sell,40100.0,2.0,BTCUSDT\n"
    )
    with zipfile.ZipFile(orderbook_path, "w") as zf:
        zf.writestr("ob_2024-01-01.csv", csv_content)

    for input_class, raw_path in {
        "klines": kline_path,
        "trades": trade_path,
        "funding": funding_path,
        "open_interest": oi_path,
        "orderbook": orderbook_path,
    }.items():
        df = bridge.read_raw(input_class, raw_path)
        norm_path, _ = bridge.write_normalized(df, input_class, symbol, date_str, str(raw_path))
        assert norm_path.exists()

    gate = BybitReadinessGate(
        catalog_root=tmp_path / "catalog",
        historical_root=historical_root,
        metrics_root=metrics_root,
        normalized_root=normalized_root,
    )
    producer = BybitProducer(base_dir=tmp_path)
    producer.readiness_gate = gate

    manifest = producer.export_snapshot(symbol=symbol, snapshot_ts=snapshot_ts, channels=["bybit_standard", "depth_weighted"])

    assert manifest.models["bybit_standard"].availability_status == "available"
    assert manifest.models["depth_weighted"].availability_status == "available"


def test_bybit_historical_export_is_deterministic_from_identical_inputs(tmp_path):
    import json
    import pandas as pd

    from src.liquidationheatmap.modeled_snapshots.bybit_readiness import BybitReadinessGate

    date_str = "2024-01-01"
    snapshot_ts = "2024-01-01T12:00:00Z"

    normalized_root = tmp_path / "normalized"
    for input_type in ["klines", "open_interest", "funding", "trades", "orderbook"]:
        normalized_path = normalized_root / input_type / "BTCUSDT-PERP.BYBIT" / f"{date_str}.parquet"
        normalized_path.parent.mkdir(parents=True, exist_ok=True)

        if input_type == "klines":
            df = pd.DataFrame({"timestamp": ["2024-01-01T11:59:00Z"], "close": [40000.0]})
        elif input_type == "open_interest":
            df = pd.DataFrame({"timestamp": ["2024-01-01T11:59:00Z"], "open_interest_value": [5000.0]})
        elif input_type == "funding":
            df = pd.DataFrame({"timestamp": ["2024-01-01T11:59:00Z"], "funding_rate": [0.0001], "next_funding_time": ["2024-01-01T16:00:00Z"], "predicted_rate": [0.0001]})
        elif input_type == "trades":
            df = pd.DataFrame({"timestamp": ["2024-01-01T11:59:00Z"], "price": [40000.0], "quantity": [20.0], "side": ["buy"], "value": [800000.0]})
        else:
            cols = {"timestamp": ["2024-01-01T11:59:00Z"], "receipt_timestamp": ["2024-01-01T11:59:00Z"], "exchange": ["bybit"], "symbol": ["BTCUSDT"]}
            for i in range(20):
                cols[f"bid_{i}_price"] = [39000.0 - i * 10]
                cols[f"bid_{i}_size"] = [1.0]
                cols[f"ask_{i}_price"] = [41000.0 + i * 10]
                cols[f"ask_{i}_size"] = [1.0]
            df = pd.DataFrame(cols)

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if "next_funding_time" in df.columns:
            df["next_funding_time"] = pd.to_datetime(df["next_funding_time"])
        if "receipt_timestamp" in df.columns:
            df["receipt_timestamp"] = pd.to_datetime(df["receipt_timestamp"])
        df.to_parquet(normalized_path)

    gate = BybitReadinessGate(
        catalog_root=tmp_path / "catalog",
        historical_root=tmp_path / "historical",
        metrics_root=tmp_path / "metrics",
        normalized_root=normalized_root,
    )

    producer_a = BybitProducer(base_dir=tmp_path / "run_a")
    producer_a.readiness_gate = gate
    producer_b = BybitProducer(base_dir=tmp_path / "run_b")
    producer_b.readiness_gate = gate

    producer_a.export_snapshot(symbol="BTCUSDT", snapshot_ts=snapshot_ts, channels=["bybit_standard", "depth_weighted"])
    producer_b.export_snapshot(symbol="BTCUSDT", snapshot_ts=snapshot_ts, channels=["bybit_standard", "depth_weighted"])

    for channel in ["bybit_standard", "depth_weighted"]:
        artifact_a = json.loads((tmp_path / "run_a" / "bybit" / "artifacts" / "BTCUSDT" / snapshot_ts / f"{channel}.json").read_text())
        artifact_b = json.loads((tmp_path / "run_b" / "bybit" / "artifacts" / "BTCUSDT" / snapshot_ts / f"{channel}.json").read_text())

        artifact_a.pop("generation_metadata", None)
        artifact_b.pop("generation_metadata", None)
        assert artifact_a == artifact_b
