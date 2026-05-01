import math
from datetime import datetime, timezone

from src.liquidationheatmap.scorecard.adaptive import (
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
