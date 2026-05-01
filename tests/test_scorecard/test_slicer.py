from datetime import datetime, timezone

import pytest

from src.liquidationheatmap.models.scorecard import ExpertSignalObservation
from src.liquidationheatmap.scorecard.slicer import ScorecardSlicer


@pytest.fixture
def observations() -> list[ExpertSignalObservation]:
    base_time = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    observations = []

    obs1_id = ExpertSignalObservation.generate_id("v1", "BTCUSDT", base_time, 59000.0, "long")
    observations.append(
        ExpertSignalObservation(
            observation_id=obs1_id,
            expert_id="v1",
            symbol="BTCUSDT",
            snapshot_ts=base_time,
            level_price=59000.0,
            side="long",
            confidence=0.9,
            reference_price=60000.0,
            distance_bps=10,
            touched=True,
            touch_ts=base_time,
            liquidation_confirmed=False,
        )
    )

    obs2_id = ExpertSignalObservation.generate_id("v1", "BTCUSDT", base_time, 58000.0, "long")
    observations.append(
        ExpertSignalObservation(
            observation_id=obs2_id,
            expert_id="v1",
            symbol="BTCUSDT",
            snapshot_ts=base_time,
            level_price=58000.0,
            side="long",
            confidence=0.85,
            reference_price=60000.0,
            distance_bps=20,
            touched=False,
            liquidation_confirmed=False,
        )
    )

    obs3_id = ExpertSignalObservation.generate_id("v1", "BTCUSDT", base_time, 61000.0, "short")
    observations.append(
        ExpertSignalObservation(
            observation_id=obs3_id,
            expert_id="v1",
            symbol="BTCUSDT",
            snapshot_ts=base_time,
            level_price=61000.0,
            side="short",
            confidence=0.5,
            reference_price=60000.0,
            distance_bps=60,
            touched=False,
            liquidation_confirmed=False,
        )
    )

    obs4_id = ExpertSignalObservation.generate_id("v3", "BTCUSDT", base_time, 50000.0, "long")
    observations.append(
        ExpertSignalObservation(
            observation_id=obs4_id,
            expert_id="v3",
            symbol="BTCUSDT",
            snapshot_ts=base_time,
            level_price=50000.0,
            side="long",
            confidence=0.1,
            reference_price=60000.0,
            distance_bps=300,
            touched=False,
            liquidation_confirmed=False,
        )
    )

    return observations


def test_slicing_observations(
    observations: list[ExpertSignalObservation],
) -> None:
    slicer = ScorecardSlicer()
    slices = slicer.slice_observations(observations)

    assert len(slices) == 3
    assert len(slices["v1:BTCUSDT:long:0-25:0.8-1.0:none"]) == 2
    assert len(slices["v1:BTCUSDT:short:50-100:0.3-0.6:none"]) == 1
    assert len(slices["v3:BTCUSDT:long:200+:0.0-0.3:none"]) == 1


def test_volatility_regime_slicing(
    observations: list[ExpertSignalObservation],
) -> None:
    slicer = ScorecardSlicer(regime_map={observations[0].snapshot_ts: "high_vol"})
    slices = slicer.slice_observations(observations)

    assert "v1:BTCUSDT:long:0-25:0.8-1.0:high_vol" in slices


def test_slicer_with_quantile_buckets(observations):
    from src.liquidationheatmap.models.scorecard import QuantileBucketSet

    distance_buckets = QuantileBucketSet(
        metric_name="distance_bps",
        n_buckets=2,
        boundaries=[0.0, 100.0, 1000.0],
        labels=["q1", "q2"],
        observation_count=4,
    )

    confidence_buckets = QuantileBucketSet(
        metric_name="confidence",
        n_buckets=2,
        boundaries=[0.0, 0.6, 1.0],
        labels=["low", "high"],
        observation_count=4,
    )

    slicer = ScorecardSlicer(
        distance_buckets=distance_buckets, confidence_buckets=confidence_buckets
    )
    slices = slicer.slice_observations(observations)

    # obs1: dist=10 (q1), conf=0.9 (high)
    # obs2: dist=20 (q1), conf=0.85 (high)
    # obs3: dist=60 (q1), conf=0.5 (low)
    # obs4: dist=300 (q2), conf=0.1 (low)

    assert "v1:BTCUSDT:long:q1:high:none" in slices
    assert len(slices["v1:BTCUSDT:long:q1:high:none"]) == 2
    assert "v1:BTCUSDT:short:q1:low:none" in slices
    assert "v3:BTCUSDT:long:q2:low:none" in slices


def test_slicer_with_inferred_regime(observations):
    ts = observations[0].snapshot_ts
    inferred_regime_map = {ts: "high_vol"}

    # Ensure it's used if passed via inferred_regime_map
    slicer = ScorecardSlicer(inferred_regime_map=inferred_regime_map)
    slices = slicer.slice_observations(observations)

    for sid in slices:
        assert "high_vol" in sid
