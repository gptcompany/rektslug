from datetime import datetime, timezone

import pytest

from src.liquidationheatmap.models.scorecard import ExpertSignalObservation
from src.liquidationheatmap.scorecard.aggregator import ScorecardAggregator


@pytest.fixture
def sample_observations() -> list[ExpertSignalObservation]:
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
            confidence=0.8,
            reference_price=60000.0,
            distance_bps=166,
            touched=True,
            touch_ts=datetime(2026, 4, 30, 12, 30, tzinfo=timezone.utc),
            liquidation_confirmed=True,
            liquidation_confirm_ts=datetime(2026, 4, 30, 12, 35, tzinfo=timezone.utc),
            mfe_bps=50,
            mae_bps=10,
            time_to_touch_secs=1800,
            time_to_liquidation_confirm_secs=300,
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
            confidence=0.9,
            reference_price=60000.0,
            distance_bps=333,
            touched=True,
            touch_ts=datetime(2026, 4, 30, 13, 0, tzinfo=timezone.utc),
            liquidation_confirmed=True,
            liquidation_confirm_ts=datetime(2026, 4, 30, 13, 10, tzinfo=timezone.utc),
            mfe_bps=100,
            mae_bps=20,
            time_to_touch_secs=3600,
            time_to_liquidation_confirm_secs=600,
        )
    )

    obs3_id = ExpertSignalObservation.generate_id("v1", "BTCUSDT", base_time, 57000.0, "long")
    observations.append(
        ExpertSignalObservation(
            observation_id=obs3_id,
            expert_id="v1",
            symbol="BTCUSDT",
            snapshot_ts=base_time,
            level_price=57000.0,
            side="long",
            confidence=0.7,
            reference_price=60000.0,
            distance_bps=500,
            touched=True,
            touch_ts=datetime(2026, 4, 30, 14, 0, tzinfo=timezone.utc),
            liquidation_confirmed=False,
            liquidation_confirm_ts=None,
            mfe_bps=10,
            mae_bps=50,
            time_to_touch_secs=7200,
            time_to_liquidation_confirm_secs=None,
        )
    )

    obs4_id = ExpertSignalObservation.generate_id("v1", "BTCUSDT", base_time, 56000.0, "long")
    observations.append(
        ExpertSignalObservation(
            observation_id=obs4_id,
            expert_id="v1",
            symbol="BTCUSDT",
            snapshot_ts=base_time,
            level_price=56000.0,
            side="long",
            confidence=0.5,
            reference_price=60000.0,
            distance_bps=666,
            touched=False,
            touch_ts=None,
            liquidation_confirmed=False,
            liquidation_confirm_ts=None,
            mfe_bps=None,
            mae_bps=None,
            time_to_touch_secs=None,
            time_to_liquidation_confirm_secs=None,
        )
    )

    return observations


def test_empirical_probability_aggregation(
    sample_observations: list[ExpertSignalObservation],
) -> None:
    aggregator = ScorecardAggregator()
    result = aggregator.aggregate_probabilities(sample_observations)

    assert result["sample_count"] == 4
    assert result["touch_count"] == 3
    assert result["touch_probability"] == 0.75
    assert result["liquidation_match_count"] == 2
    assert result["liquidation_match_probability_given_touch"] == pytest.approx(0.6666, 0.001)


def test_quantile_aggregation(
    sample_observations: list[ExpertSignalObservation],
) -> None:
    aggregator = ScorecardAggregator()
    result = aggregator.aggregate_quantiles(sample_observations)

    assert result["mfe_quantiles"]["p50"] == 50
    assert result["mfe_quantiles"]["p90"] == 90
    assert result["mae_quantiles"]["p50"] == 20
    assert result["time_to_touch_quantiles"]["p50"] == 3600
    assert result["time_to_liquidation_confirm_quantiles"]["p50"] == 450


def test_low_sample_flag_for_non_empty_population(
    sample_observations: list[ExpertSignalObservation],
) -> None:
    aggregator = ScorecardAggregator(min_samples=10)
    result = aggregator.aggregate_probabilities(sample_observations)

    assert result["sample_count"] == 4
    assert result["low_sample_flag"] is True
