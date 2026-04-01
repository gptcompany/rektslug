from __future__ import annotations

import json
from pathlib import Path

from scripts.compare_hl_sidecar_vs_coinglass import (
    BucketedDistribution,
    compute_metrics,
    load_sidecar_artifact,
)
from scripts.precompute_hl_sidecar import _compute_display_range


def test_load_sidecar_artifact_supports_modern_cache_schema(tmp_path: Path) -> None:
    payload = {
        "source": "hyperliquid-sidecar",
        "symbol": "BTCUSDT",
        "current_price": 68500.0,
        "account_count": 123,
        "bin_size": 10.0,
        "grid": {
            "min_price": 50000.0,
            "max_price": 90000.0,
        },
        "long_buckets": [
            {"price_level": 64000.0, "leverage": "cross", "volume": 1000.0},
        ],
        "short_buckets": [
            {"price_level": 72000.0, "leverage": "cross", "volume": 1500.0},
        ],
    }
    path = tmp_path / "cache.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    distribution = load_sidecar_artifact(path)

    assert distribution.symbol == "BTC"
    assert distribution.current_price == 68500.0
    assert distribution.account_count == 123
    assert distribution.display_min_price == 50000.0
    assert distribution.display_max_price == 90000.0
    assert distribution.long_buckets == {64000.0: 1000.0}
    assert distribution.short_buckets == {72000.0: 1500.0}


def test_compute_metrics_reports_coarse_and_cumulative_shape() -> None:
    sidecar = BucketedDistribution(
        source="sidecar",
        symbol="ETH",
        bin_size=1.0,
        current_price=2000.0,
    )
    coinglass = BucketedDistribution(
        source="coinglass",
        symbol="ETH",
        bin_size=1.0,
        current_price=2000.0,
    )

    for offset in range(10, 160, 10):
        sidecar.long_buckets[2000.0 - offset] = 200.0 - offset
        sidecar.short_buckets[2000.0 + offset] = 190.0 - (offset / 2.0)
        coinglass.long_buckets[2000.0 - offset] = (200.0 - offset) * 1.03
        coinglass.short_buckets[2000.0 + offset] = (190.0 - (offset / 2.0)) * 0.97

    metrics = compute_metrics(sidecar, coinglass)

    assert metrics["coarse_shape"]
    assert metrics["cumulative_shape"]
    assert all(item["pearson_r"] > 0.95 for item in metrics["coarse_shape"].values())
    assert all(item["pearson_r"] > 0.99 for item in metrics["cumulative_shape"].values())


def test_compute_display_range_preserves_most_side_volume() -> None:
    long_buckets = {
        96.0: 10.0,
        90.0: 20.0,
        82.0: 120.0,
        76.0: 15.0,
    }
    short_buckets = {
        104.0: 10.0,
        110.0: 20.0,
        128.0: 140.0,
        136.0: 10.0,
    }

    min_price, max_price = _compute_display_range(long_buckets, short_buckets, 100.0)

    assert min_price < 100.0 < max_price
    assert min_price <= 82.0
    assert max_price >= 128.0
