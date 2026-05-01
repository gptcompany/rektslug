from datetime import datetime, timezone

import pytest

from src.liquidationheatmap.models.scorecard import ExpertSignalObservation
from src.liquidationheatmap.scorecard.slicer import ScorecardSlicer


@pytest.fixture
def observations() -> list[ExpertSignalObservation]:
    base_time = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    observations = []

    obs1_id = ExpertSignalObservation.generate_id(
        "v1", "BTCUSDT", base_time, 59000.0, "long"
    )
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

    obs2_id = ExpertSignalObservation.generate_id(
        "v1", "BTCUSDT", base_time, 58000.0, "long"
    )
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

    obs3_id = ExpertSignalObservation.generate_id(
        "v1", "BTCUSDT", base_time, 61000.0, "short"
    )
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

    obs4_id = ExpertSignalObservation.generate_id(
        "v3", "BTCUSDT", base_time, 50000.0, "long"
    )
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
