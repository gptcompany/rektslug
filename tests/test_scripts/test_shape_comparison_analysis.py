"""Regression tests for scripts/shape_comparison_analysis.py."""

from __future__ import annotations

import json

import pytest

from scripts import shape_comparison_analysis as analysis


class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def test_load_rektslug_reads_price_level_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "current_price": 100.0,
        "long_buckets": [
            {"price_level": 90.0, "volume": 10.0},
            {"price_level": 92.0, "volume": 20.0},
            {"price_level": 94.0, "volume": 30.0},
        ],
        "short_buckets": [
            {"price_level": 106.0, "volume": 40.0},
            {"price_level": 108.0, "volume": 50.0},
        ],
    }

    monkeypatch.setattr(
        analysis.urllib.request,
        "urlopen",
        lambda request, timeout=10: _FakeHttpResponse(payload),
    )

    dist = analysis.load_rektslug({"symbol": "ETHUSDT", "timeframe": "1d"})

    assert dist.valid is True
    assert dist.error == ""
    assert dist.raw_prices.tolist() == [90.0, 92.0, 94.0, 106.0, 108.0]
    assert dist.raw_volumes.tolist() == [10.0, 20.0, 30.0, 40.0, 50.0]
    assert 0.0 not in dist.raw_prices.tolist()
