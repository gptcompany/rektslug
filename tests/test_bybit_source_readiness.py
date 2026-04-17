import pytest
from datetime import datetime, timezone
from src.liquidationheatmap.modeled_snapshots.bybit_readiness import BybitReadinessGate


def _gate(tmp_path):
    return BybitReadinessGate(
        catalog_root=tmp_path / "catalog",
        historical_root=tmp_path / "historical",
        metrics_root=tmp_path / "metrics",
    )


def _touch_catalog_file(tmp_path, input_type, symbol="BTCUSDT", date_str="2026-04-07"):
    path = tmp_path / "catalog" / input_type / f"{symbol}-PERP.BYBIT" / f"{date_str}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def _touch_standard_catalog_files(tmp_path, date_str="2026-04-07"):
    for input_type in ["ohlcv", "open_interest", "funding_rate", "trades"]:
        _touch_catalog_file(tmp_path, input_type, date_str=date_str)


def test_bybit_readiness_report_shape(tmp_path):
    gate = _gate(tmp_path)
    report = gate.check_readiness("BTCUSDT", "2026-04-07T12:00:00Z", "bybit_standard")
    
    assert report.exchange == "bybit"
    assert report.snapshot_ts == "2026-04-07T12:00:00Z"
    assert isinstance(report.details, dict)
    assert "klines" in report.details
    assert "open_interest" in report.details
    assert "funding" in report.details
    assert "trades" in report.details


def test_bybit_readiness_orderbook_gap(tmp_path):
    gate = _gate(tmp_path)
    # Gap is 2025-08-21 to 2026-04-05
    gap_ts = "2025-12-01T12:00:00Z"
    _touch_standard_catalog_files(tmp_path, date_str="2025-12-01")
    _touch_catalog_file(tmp_path, "orderbook", date_str="2025-12-01")

    report = gate.check_readiness("BTCUSDT", gap_ts, "depth_weighted")
    
    assert report.status == "blocked_source_missing"
    assert report.details["orderbook"]["status"] == "in_gap"


def test_bybit_readiness_gap_includes_2026_04_05(tmp_path):
    gate = _gate(tmp_path)
    _touch_standard_catalog_files(tmp_path, date_str="2026-04-05")
    _touch_catalog_file(tmp_path, "orderbook", date_str="2026-04-05")

    report = gate.check_readiness("BTCUSDT", "2026-04-05T12:00:00Z", "depth_weighted")

    assert report.status == "blocked_source_missing"
    assert report.details["orderbook"]["status"] == "in_gap"


def test_bybit_readiness_available_live(tmp_path):
    gate = _gate(tmp_path)
    # Live catalog starts 2026-04-06
    live_ts = "2026-04-07T12:00:00Z"
    _touch_standard_catalog_files(tmp_path, date_str="2026-04-07")
    _touch_catalog_file(tmp_path, "orderbook", date_str="2026-04-07")

    report = gate.check_readiness("BTCUSDT", live_ts, "depth_weighted")
    
    assert report.status == "available"
    assert report.details["funding"]["source_status"] == "catalog_file"
    assert report.details["orderbook"]["source_status"] == "catalog_file"


def test_bybit_readiness_historical_only_is_not_marked_available(tmp_path):
    gate = _gate(tmp_path)
    date_str = "2024-01-01"
    _touch_standard_catalog_files(tmp_path, date_str=date_str)
    orderbook_path = (
        tmp_path
        / "historical"
        / "orderbook"
        / "contract"
        / "BTCUSDT"
        / "contract"
        / "orderbook"
        / "BTCUSDT"
        / "2024-01-01_BTCUSDT_ob500.data.zip"
    )
    orderbook_path.parent.mkdir(parents=True, exist_ok=True)
    orderbook_path.touch()

    report = gate.check_readiness("BTCUSDT", "2024-01-01T12:00:00Z", "depth_weighted")

    assert report.status == "blocked_source_unverified"
    assert report.details["orderbook"]["source_status"] == "historical_raw_unnormalized"
    assert "historical bridge" in report.details["orderbook"]["reason"]
    assert "ccxt-data-pipeline" not in report.details["orderbook"]["reason"]


def test_bybit_readiness_reason_mentions_bridge_for_raw_metrics(tmp_path):
    gate = _gate(tmp_path)
    date_str = "2024-01-01"
    # Touch klines in catalog so only funding hits the metrics path
    _touch_catalog_file(tmp_path, "ohlcv", date_str=date_str)
    _touch_catalog_file(tmp_path, "open_interest", date_str=date_str)
    _touch_catalog_file(tmp_path, "trades", date_str=date_str)
    # Create a raw metric file that matches the glob pattern
    funding_dir = tmp_path / "metrics" / "funding_rates"
    funding_dir.mkdir(parents=True, exist_ok=True)
    (funding_dir / "BTCUSDT_2024.json").touch()

    report = gate.check_readiness("BTCUSDT", "2024-01-01T12:00:00Z", "bybit_standard")

    assert report.details["funding"]["source_status"] == "historical_raw_unnormalized"
    assert "historical bridge" in report.details["funding"]["reason"]
    assert "ccxt-data-pipeline" not in report.details["funding"]["reason"]


def test_bybit_readiness_normalized_historical_clears_unverified(tmp_path):
    # Setup gate with a normalized_root
    gate = BybitReadinessGate(
        catalog_root=tmp_path / "catalog",
        historical_root=tmp_path / "historical",
        metrics_root=tmp_path / "metrics",
        normalized_root=tmp_path / "normalized",
    )
    
    date_str = "2024-01-01"
    
    # Touch normalized parquet files instead of catalog
    for input_type in ["klines", "open_interest", "funding", "trades", "orderbook"]:
        normalized_path = tmp_path / "normalized" / input_type / "BTCUSDT-PERP.BYBIT" / f"{date_str}.parquet"
        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.touch()

    report = gate.check_readiness("BTCUSDT", "2024-01-01T12:00:00Z", "depth_weighted")

    assert report.status == "available"
    assert report.details["orderbook"]["source_status"] == "normalized_historical"
    assert report.details["trades"]["source_status"] == "normalized_historical"
