"""Unit tests for spec-018 calibration helpers."""

from scripts.run_ank_calibration import aligned_bucket_overlap


def test_aligned_bucket_overlap_handles_different_steps():
    local_prices = [100.0, 101.0, 102.0]
    provider_prices = [100.0, 100.5, 101.0, 101.5, 102.0]

    overlap = aligned_bucket_overlap(local_prices, provider_prices)

    assert overlap == 1.0


def test_aligned_bucket_overlap_returns_zero_for_disjoint_ranges():
    local_prices = [100.0, 101.0, 102.0]
    provider_prices = [110.0, 111.0, 112.0]

    overlap = aligned_bucket_overlap(local_prices, provider_prices)

    assert overlap == 0.0
