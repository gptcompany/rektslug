import math
from datetime import datetime, timezone

from src.liquidationheatmap.scorecard.adaptive import (
    compute_realized_volatility,
    extract_volume,
)


def test_compute_realized_volatility_known_returns():
    # log returns = math.log(P_t / P_{t-1})
    # Let's say we have prices that give specific log returns.
    # Prices: 100, 101, 100
    # R1 = ln(101/100) = 0.00995033
    # R2 = ln(100/101) = -0.00995033
    # Mean = 0
    # Variance = ((0.00995033 - 0)^2 + (-0.00995033 - 0)^2) / 1 = 0.00019802
    # Std dev = 0.0140719579
    # Annualized = 0.0140719579 * sqrt(525600) = 10.202
    # In bps = 102020 (approx)

    price_path = [
        {"timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc), "price": 100.0},
        {"timestamp": datetime(2023, 1, 1, 0, 1, tzinfo=timezone.utc), "price": 101.0},
        {"timestamp": datetime(2023, 1, 1, 0, 2, tzinfo=timezone.utc), "price": 100.0},
    ]

    vol_bps = compute_realized_volatility(
        price_path=price_path,
        timestamp=datetime(2023, 1, 1, 0, 2, tzinfo=timezone.utc),
        lookback_ticks=3
    )

    # We can pre-calculate the exact expected value
    r1 = math.log(101.0 / 100.0)
    r2 = math.log(100.0 / 101.0)
    var = (r1**2 + r2**2) / 1.0
    std = math.sqrt(var)
    expected_vol = int(std * math.sqrt(525600) * 10000)

    assert vol_bps == expected_vol


def test_compute_realized_volatility_insufficient_data():
    price_path = [
        {"timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc), "price": 100.0},
    ]
    vol_bps = compute_realized_volatility(
        price_path=price_path,
        timestamp=datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc),
        lookback_ticks=10
    )
    assert vol_bps == 0


def test_extract_volume_contract():
    # Valid volume
    tick1 = {"timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc), "price": 100.0, "volume": 1500.5}
    assert extract_volume(tick1) == 1500.5

    # String volume (sometimes from APIs)
    tick2 = {"timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc), "price": 100.0, "volume": "2000.1"}
    assert extract_volume(tick2) == 2000.1

    # No volume
    tick3 = {"timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc), "price": 100.0}
    assert extract_volume(tick3) is None

    # None volume
    tick4 = {"timestamp": datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc), "price": 100.0, "volume": None}
    assert extract_volume(tick4) is None
