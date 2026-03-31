"""Tests for Hyperliquid reserved-margin defaults."""

from src.liquidationheatmap.hyperliquid.margin_math import DEFAULT_RESERVED_MARGIN_CANDIDATE


def test_default_reserved_margin_candidate_is_b():
    assert DEFAULT_RESERVED_MARGIN_CANDIDATE == "B"
