"""Unit tests for spec-019 Coinglass calibration helpers."""

from scripts.run_glass_calibration import (
    GLASS_IMPROVEMENT_THRESHOLDS,
    normalize_report_timeframe,
)


def test_normalize_report_timeframe_maps_coinglass_labels():
    assert normalize_report_timeframe("1 day") == "1d"
    assert normalize_report_timeframe("7 day") == "1w"
    assert normalize_report_timeframe("1d") == "1d"


def test_glass_thresholds_relax_bucket_overlap_only():
    assert GLASS_IMPROVEMENT_THRESHOLDS["bucket_overlap"] == 0.05
    assert GLASS_IMPROVEMENT_THRESHOLDS["bucket_count_proximity"] == 0.20
