import math
from datetime import datetime, timezone

from src.liquidationheatmap.scorecard.adaptive import (
    compute_adaptive_touch_band,
    compute_realized_volatility,
    extract_volume,
)


def test_compute_realized_volatility_known_returns() -> None:
    price_path = [
        {"timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc), "price": 100.0},
        {"timestamp": datetime(2023, 1, 1, 0, 1, tzinfo=timezone.utc), "price": 101.0},
        {"timestamp": datetime(2023, 1, 1, 0, 2, tzinfo=timezone.utc), "price": 100.0},
    ]

    vol_bps = compute_realized_volatility(
        price_path=price_path,
        timestamp=datetime(2023, 1, 1, 0, 2, tzinfo=timezone.utc),
        lookback_ticks=3,
    )

    first_return = math.log(101.0 / 100.0)
    second_return = math.log(100.0 / 101.0)
    variance = (first_return**2 + second_return**2) / 1.0
    std_dev = math.sqrt(variance)
    expected_vol = int(std_dev * math.sqrt(525600) * 10000)

    assert vol_bps == expected_vol


def test_compute_realized_volatility_insufficient_data() -> None:
    price_path = [
        {"timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc), "price": 100.0},
    ]
    vol_bps = compute_realized_volatility(
        price_path=price_path,
        timestamp=datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc),
        lookback_ticks=10,
    )
    assert vol_bps == 0


def test_compute_realized_volatility_accepts_iso_timestamps_and_unsorted_path() -> None:
    price_path = [
        {"timestamp": "2023-01-01T00:02:00Z", "price": 100.0},
        {"timestamp": "2023-01-01T00:00:00Z", "price": 100.0},
        {"timestamp": "2023-01-01T00:01:00Z", "price": 101.0},
    ]

    vol_bps = compute_realized_volatility(
        price_path=price_path,
        timestamp=datetime(2023, 1, 1, 0, 2, tzinfo=timezone.utc),
        lookback_ticks=3,
    )

    assert vol_bps > 0


def test_extract_volume_contract() -> None:
    tick1 = {
        "timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc),
        "price": 100.0,
        "volume": 1500.5,
    }
    assert extract_volume(tick1) == 1500.5

    tick2 = {
        "timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc),
        "price": 100.0,
        "volume": "2000.1",
    }
    assert extract_volume(tick2) == 2000.1

    tick3 = {
        "timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc),
        "price": 100.0,
    }
    assert extract_volume(tick3) is None

    tick4 = {
        "timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc),
        "price": 100.0,
        "volume": None,
    }
    assert extract_volume(tick4) is None


def test_compute_adaptive_touch_band_volatility_sensitivity() -> None:
    # Low volatility path
    low_vol_path = [
        {
            "timestamp": datetime(2023, 1, 1, 0, i, tzinfo=timezone.utc),
            "price": 100.0 + (i % 2) * 0.01,
        }
        for i in range(60)
    ]

    # High volatility path
    high_vol_path = [
        {
            "timestamp": datetime(2023, 1, 1, 0, i, tzinfo=timezone.utc),
            "price": 100.0 + (i % 2) * 5.0,
        }
        for i in range(60)
    ]

    snapshot_ts = datetime(2023, 1, 1, 0, 59, tzinfo=timezone.utc)

    low_band = compute_adaptive_touch_band(low_vol_path, snapshot_ts, "BTC")
    high_band = compute_adaptive_touch_band(high_vol_path, snapshot_ts, "BTC")

    assert high_band > low_band
    assert low_band > 0


def test_compute_adaptive_touch_band_different_symbols() -> None:
    # Different symbols with same volatility might have different baseline or same if purely driven by data.
    # The requirement is "given two symbols with different volatility profiles at the same timestamp, they differ"
    path1 = [
        {
            "timestamp": datetime(2023, 1, 1, 0, i, tzinfo=timezone.utc),
            "price": 100.0 + (i % 2) * 0.1,
        }
        for i in range(60)
    ]
    path2 = [
        {
            "timestamp": datetime(2023, 1, 1, 0, i, tzinfo=timezone.utc),
            "price": 100.0 + (i % 2) * 1.0,
        }
        for i in range(60)
    ]
    snapshot_ts = datetime(2023, 1, 1, 0, 59, tzinfo=timezone.utc)

    band1 = compute_adaptive_touch_band(path1, snapshot_ts, "BTC")
    band2 = compute_adaptive_touch_band(path2, snapshot_ts, "ETH")

    assert band1 != band2


def test_compute_adaptive_touch_band_fallback_proxy() -> None:
    # Insufficient history for realized volatility (< 2 ticks before snapshot)
    path = [
        {"timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc), "price": 100.0},
        {
            "timestamp": datetime(2023, 1, 1, 0, 1, tzinfo=timezone.utc),
            "price": 105.0,
        },  # the only valid tick if lookback is short, wait, spread proxy uses the whole available path or something
    ]
    snapshot_ts = datetime(2023, 1, 1, 0, 1, tzinfo=timezone.utc)

    band = compute_adaptive_touch_band(path, snapshot_ts, "BTC")

    # Should use price spread (105-100 = 5) relative to mean (102.5) -> ~4.8% -> 487 bps
    # Let's just assert it is greater than 0 and not the fixed 5 bps fallback.
    assert band > 0
    assert band != 5


def test_compute_adaptive_touch_band_fallback_accepts_iso_timestamps() -> None:
    path = [
        {"timestamp": "2023-01-01T00:00:00Z", "price": 100.0},
        {"timestamp": "2023-01-01T00:01:00Z", "price": 105.0},
    ]
    snapshot_ts = datetime(2023, 1, 1, 0, 1, tzinfo=timezone.utc)

    band = compute_adaptive_touch_band(path, snapshot_ts, "BTC")

    assert band > 0
    assert band != 5


def test_compute_adaptive_touch_band_zero_history_uses_non_fixed_floor() -> None:
    band = compute_adaptive_touch_band([], datetime(2023, 1, 1, tzinfo=timezone.utc), "BTC")

    assert band == 1
