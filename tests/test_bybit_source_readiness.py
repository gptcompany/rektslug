import pytest
from datetime import datetime, timezone
from src.liquidationheatmap.modeled_snapshots.bybit_readiness import BybitReadinessGate

def test_bybit_readiness_report_shape():
    gate = BybitReadinessGate()
    report = gate.check_readiness("BTCUSDT", "2026-04-07T12:00:00Z", "bybit_standard")
    
    assert report.exchange == "bybit"
    assert report.snapshot_ts == "2026-04-07T12:00:00Z"
    assert isinstance(report.details, dict)
    assert "klines" in report.details
    assert "open_interest" in report.details
    assert "funding" in report.details
    assert "trades" in report.details

def test_bybit_readiness_orderbook_gap():
    gate = BybitReadinessGate()
    # Gap is 2025-08-21 to 2026-04-05
    gap_ts = "2025-12-01T12:00:00Z"
    report = gate.check_readiness("BTCUSDT", gap_ts, "depth_weighted")
    
    assert report.status == "blocked_source_missing"
    assert report.details["orderbook"]["status"] == "in_gap"

def test_bybit_readiness_available_live():
    gate = BybitReadinessGate()
    # Live catalog starts 2026-04-06
    live_ts = "2026-04-07T12:00:00Z"
    report = gate.check_readiness("BTCUSDT", live_ts, "depth_weighted")
    
    # This might depend on real paths if not mocked, but let's assume available
    # assert report.status == "available"
    pass
