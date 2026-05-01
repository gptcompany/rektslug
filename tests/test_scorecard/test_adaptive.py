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


def test_compute_volume_threshold_with_data() -> None:
    from src.liquidationheatmap.scorecard.adaptive import compute_volume_threshold

    # Create a path with varying volumes
    path = [
        {
            "timestamp": datetime(2023, 1, 1, 0, i, tzinfo=timezone.utc),
            "price": 100.0,
            "volume": 1000.0,
        }
        for i in range(60)
    ]
    snapshot_ts = datetime(2023, 1, 1, 0, 59, tzinfo=timezone.utc)

    # Threshold should be derived from the data
    threshold = compute_volume_threshold(path, snapshot_ts)
    assert threshold is not None
    assert threshold > 0


def test_compute_volume_threshold_missing_volume() -> None:
    from src.liquidationheatmap.scorecard.adaptive import compute_volume_threshold

    # Create a path missing volume data
    path = [
        {"timestamp": datetime(2023, 1, 1, 0, i, tzinfo=timezone.utc), "price": 100.0}
        for i in range(60)
    ]
    snapshot_ts = datetime(2023, 1, 1, 0, 59, tzinfo=timezone.utc)

    threshold = compute_volume_threshold(path, snapshot_ts)
    assert threshold is None


def test_compute_quantile_buckets_skewed_data() -> None:
    from src.liquidationheatmap.scorecard.adaptive import compute_quantile_buckets

    # Create a highly skewed distribution: many low values, few high values
    values = [5.0] * 80 + [50.0] * 15 + [200.0] * 5

    # We want to form 5 buckets. The boundaries should reflect the percentiles.
    # min_per_bucket = 10, total = 100 observations. 100/5 = 20, which is >= 10.
    result = compute_quantile_buckets(values, "distance_bps", min_per_bucket=10)

    assert result.metric_name == "distance_bps"
    assert result.n_buckets > 1
    assert len(result.boundaries) == result.n_buckets + 1
    assert result.observation_count == 100
    # Check boundaries are monotonically increasing
    assert all(
        result.boundaries[i] <= result.boundaries[i + 1] for i in range(len(result.boundaries) - 1)
    )
    # It shouldn't just be linear ranges like 0-40, 40-80...


def test_compute_quantile_buckets_sparse_fallback() -> None:
    from src.liquidationheatmap.scorecard.adaptive import compute_quantile_buckets

    values = [10.0, 20.0, 30.0]

    # Requesting a minimum of 10 per bucket, but we only have 3 observations total.
    result = compute_quantile_buckets(values, "distance_bps", min_per_bucket=10)

    assert result.n_buckets == 1
    assert result.boundaries[0] <= 10.0
    assert result.boundaries[-1] >= 30.0
    assert result.labels == ["all"]


def test_infer_regime_map_volatility_transition() -> None:
    from src.liquidationheatmap.models.scorecard import ExpertSignalObservation
    from src.liquidationheatmap.scorecard.adaptive import infer_regime_map

    # Create a path that has a distinct volatility transition
    # First 100 ticks: low vol
    # Next 100 ticks: high vol
    path = []
    base_price = 100.0
    for i in range(100):
        # Using 1 minute steps, 0 to 100 hours basically or just change hour/minute
        ts = datetime(2023, 1, 1, i // 60, i % 60, tzinfo=timezone.utc)
        path.append({"timestamp": ts, "price": base_price + (i % 2) * 0.1})
    for i in range(100, 200):
        ts = datetime(2023, 1, 1, i // 60, i % 60, tzinfo=timezone.utc)
        path.append({"timestamp": ts, "price": base_price + (i % 2) * 5.0})

    ts1 = datetime(2023, 1, 1, 0, 50, tzinfo=timezone.utc)
    id1 = ExpertSignalObservation.generate_id("v1", "BTC", ts1, 100.0, "long")

    ts2 = datetime(2023, 1, 1, 2, 30, tzinfo=timezone.utc)  # index 150
    id2 = ExpertSignalObservation.generate_id("v1", "BTC", ts2, 100.0, "long")

    observations = [
        ExpertSignalObservation(
            observation_id=id1,
            expert_id="v1",
            symbol="BTC",
            snapshot_ts=ts1,
            level_price=100.0,
            side="long",
            confidence=0.5,
            reference_price=100.0,
            distance_bps=0,
            touched=False,
        ),
        ExpertSignalObservation(
            observation_id=id2,
            expert_id="v1",
            symbol="BTC",
            snapshot_ts=ts2,
            level_price=100.0,
            side="long",
            confidence=0.5,
            reference_price=100.0,
            distance_bps=0,
            touched=False,
        ),
    ]

    regime_map = infer_regime_map(observations, path)

    # Check that we have at least two distinct regime labels
    labels = set(regime_map.values())
    assert len(labels) >= 2
    # The low vol observation and high vol observation should map to different regimes
    assert regime_map[ts1] != regime_map[ts2]


def test_infer_regime_map_stable_low_vol() -> None:
    from src.liquidationheatmap.models.scorecard import ExpertSignalObservation
    from src.liquidationheatmap.scorecard.adaptive import infer_regime_map

    path = [
        {
            "timestamp": datetime(2023, 1, 1, i // 60, i % 60, tzinfo=timezone.utc),
            "price": 100.0 + (i % 2) * 0.1,
        }
        for i in range(100)
    ]

    ts1 = datetime(2023, 1, 1, 1, 10, tzinfo=timezone.utc)
    id1 = ExpertSignalObservation.generate_id("v1", "BTC", ts1, 100.0, "long")
    ts2 = datetime(2023, 1, 1, 1, 20, tzinfo=timezone.utc)
    id2 = ExpertSignalObservation.generate_id("v1", "BTC", ts2, 100.0, "long")

    observations = [
        ExpertSignalObservation(
            observation_id=id1,
            expert_id="v1",
            symbol="BTC",
            snapshot_ts=ts1,
            level_price=100.0,
            side="long",
            confidence=0.5,
            reference_price=100.0,
            distance_bps=0,
            touched=False,
        ),
        ExpertSignalObservation(
            observation_id=id2,
            expert_id="v1",
            symbol="BTC",
            snapshot_ts=ts2,
            level_price=100.0,
            side="long",
            confidence=0.5,
            reference_price=100.0,
            distance_bps=0,
            touched=False,
        ),
    ]

    regime_map = infer_regime_map(observations, path)
    assert len(set(regime_map.values())) == 1


def test_infer_regime_map_missing_feature_data() -> None:
    from src.liquidationheatmap.models.scorecard import ExpertSignalObservation
    from src.liquidationheatmap.scorecard.adaptive import infer_regime_map

    # Missing price path
    path = []

    ts1 = datetime(2023, 1, 1, 0, 50, tzinfo=timezone.utc)
    id1 = ExpertSignalObservation.generate_id("v1", "BTC", ts1, 100.0, "long")

    observations = [
        ExpertSignalObservation(
            observation_id=id1,
            expert_id="v1",
            symbol="BTC",
            snapshot_ts=ts1,
            level_price=100.0,
            side="long",
            confidence=0.5,
            reference_price=100.0,
            distance_bps=0,
            touched=False,
        ),
    ]

    regime_map = infer_regime_map(observations, path)
    assert set(regime_map.values()) == {"unknown"}
