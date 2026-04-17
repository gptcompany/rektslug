import json
import zipfile
import pytest
from pathlib import Path
from src.liquidationheatmap.modeled_snapshots.bybit_historical_bridge import BybitHistoricalBridge


def _make_bridge(tmp_path):
    return BybitHistoricalBridge(
        historical_root=tmp_path / "historical",
        normalized_root=tmp_path / "normalized",
        metrics_root=tmp_path / "metrics",
    )


# --- resolve_raw_path ---

def test_resolve_raw_path_klines(tmp_path):
    bridge = _make_bridge(tmp_path)
    path = bridge.resolve_raw_path("BTCUSDT", "2024-01-01", "klines")
    assert path == tmp_path / "historical" / "klines" / "linear" / "BTCUSDT" / "1m" / "BTCUSDT_1m_2024-01-01.json"


def test_resolve_raw_path_funding(tmp_path):
    bridge = _make_bridge(tmp_path)
    path = bridge.resolve_raw_path("BTCUSDT", "2024-01-01", "funding")
    assert path == tmp_path / "metrics" / "funding_rates" / "BTCUSDT" / "2024-01-01.json"


def test_resolve_raw_path_open_interest(tmp_path):
    bridge = _make_bridge(tmp_path)
    path = bridge.resolve_raw_path("BTCUSDT", "2024-01-01", "open_interest")
    assert path == tmp_path / "metrics" / "open_interest" / "BTCUSDT" / "2024-01-01.json"


def test_resolve_raw_path_orderbook(tmp_path):
    bridge = _make_bridge(tmp_path)
    path = bridge.resolve_raw_path("BTCUSDT", "2024-01-01", "orderbook")
    assert "ob500.data.zip" in str(path)


# --- klines reader ---

def test_read_and_write_normalized_klines(tmp_path):
    bridge = _make_bridge(tmp_path)

    raw_path = tmp_path / "historical" / "klines" / "linear" / "BTCUSDT" / "1m" / "BTCUSDT_1m_2024-01-01.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text('[[1704067200000, "40000.0", "40100.0", "39900.0", "40050.0", "1.5", "60000.0"]]')

    df = bridge.read_raw("klines", raw_path)
    assert not df.empty
    assert "close" in df.columns
    assert "timestamp" in df.columns

    normalized_path, meta = bridge.write_normalized(df, "klines", "BTCUSDT", "2024-01-01", str(raw_path))
    assert normalized_path.exists()
    assert meta["source_path"] == str(raw_path)
    assert meta["digest"] is not None


# --- funding reader ---

def test_read_funding_json_array(tmp_path):
    bridge = _make_bridge(tmp_path)
    path = tmp_path / "funding.json"
    data = [
        {"funding_rate": "0.0001", "funding_rate_timestamp": 1704067200000},
        {"funding_rate": "0.0002", "funding_rate_timestamp": 1704096000000},
    ]
    path.write_text(json.dumps(data))

    df = bridge.read_raw("funding", path)
    assert not df.empty
    assert "funding_rate" in df.columns
    assert "timestamp" in df.columns
    assert len(df) == 2
    assert df["funding_rate"].iloc[0] == pytest.approx(0.0001)


def test_read_funding_wrapped_result(tmp_path):
    bridge = _make_bridge(tmp_path)
    path = tmp_path / "funding.json"
    data = {"result": [{"funding_rate": "0.0003", "funding_rate_timestamp": 1704067200000}]}
    path.write_text(json.dumps(data))

    df = bridge.read_raw("funding", path)
    assert not df.empty
    assert len(df) == 1


def test_write_normalized_funding(tmp_path):
    bridge = _make_bridge(tmp_path)
    path = tmp_path / "funding.json"
    path.write_text(json.dumps([{"funding_rate": "0.0001", "funding_rate_timestamp": 1704067200000}]))

    df = bridge.read_raw("funding", path)
    norm_path, meta = bridge.write_normalized(df, "funding", "BTCUSDT", "2024-01-01", str(path))
    assert norm_path.exists()
    assert "digest" in meta


# --- open_interest reader ---

def test_read_open_interest_json_array(tmp_path):
    bridge = _make_bridge(tmp_path)
    path = tmp_path / "oi.json"
    data = [
        {"open_interest": "50000.5", "timestamp": 1704067200000},
        {"open_interest": "51000.0", "timestamp": 1704096000000},
    ]
    path.write_text(json.dumps(data))

    df = bridge.read_raw("open_interest", path)
    assert not df.empty
    assert "open_interest_value" in df.columns
    assert "timestamp" in df.columns
    assert len(df) == 2
    assert df["open_interest_value"].iloc[0] == pytest.approx(50000.5)


def test_read_open_interest_wrapped_result(tmp_path):
    bridge = _make_bridge(tmp_path)
    path = tmp_path / "oi.json"
    data = {"result": [{"open_interest": "99999", "timestamp": 1704067200000}]}
    path.write_text(json.dumps(data))

    df = bridge.read_raw("open_interest", path)
    assert not df.empty
    assert len(df) == 1


# --- orderbook reader ---

def test_read_orderbook_zip(tmp_path):
    bridge = _make_bridge(tmp_path)

    # Create a minimal zip with a CSV inside
    csv_content = "timestamp,side,price,size\n1704067200000,Buy,40000.0,1.5\n1704067200000,Sell,40100.0,2.0\n"
    zip_path = tmp_path / "2024-01-01_BTCUSDT_ob500.data.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("ob_2024-01-01.csv", csv_content)

    df = bridge.read_raw("orderbook", zip_path)
    assert not df.empty
    assert "price" in df.columns
    assert "side" in df.columns
    assert "timestamp" in df.columns
    assert len(df) == 2


def test_read_orderbook_missing_file_returns_empty(tmp_path):
    bridge = _make_bridge(tmp_path)
    df = bridge.read_raw("orderbook", tmp_path / "nonexistent.zip")
    assert df.empty


# --- edge cases ---

def test_read_raw_missing_file_returns_empty(tmp_path):
    bridge = _make_bridge(tmp_path)
    for cls in ["klines", "trades", "funding", "open_interest", "orderbook"]:
        df = bridge.read_raw(cls, tmp_path / "missing")
        assert df.empty, f"{cls} should return empty for missing file"
