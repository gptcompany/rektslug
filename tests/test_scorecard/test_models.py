from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.liquidationheatmap.models.scorecard import (
    BootstrapDominanceResult,
    ExpertScorecardSlice,
    ExpertSignalObservation,
    QuantileBucketSet,
)


def test_expert_signal_observation_optional_adaptive_fields() -> None:
    observation_id = ExpertSignalObservation.generate_id(
        "exp1", "BTC", datetime(2023, 1, 1, tzinfo=timezone.utc), 10000.0, "long"
    )
    observation = ExpertSignalObservation(
        observation_id=observation_id,
        expert_id="exp1",
        symbol="BTC",
        snapshot_ts=datetime(2023, 1, 1, tzinfo=timezone.utc),
        level_price=10000.0,
        side="long",
        confidence=0.9,
        reference_price=9900.0,
        distance_bps=100,
        touched=False,
        adaptive_touch_band_bps=15,
        local_volatility_bps=50000,
        volume_at_touch=123.45,
        volume_window_complete=True,
        post_touch_volume=456.78,
        inferred_regime="high_vol",
    )

    assert observation.adaptive_touch_band_bps == 15
    assert observation.local_volatility_bps == 50000
    assert observation.volume_at_touch == 123.45
    assert observation.volume_window_complete is True
    assert observation.post_touch_volume == 456.78
    assert observation.inferred_regime == "high_vol"


def test_expert_scorecard_slice_optional_bucket_boundaries() -> None:
    slice_id = ExpertScorecardSlice.generate_slice_id("exp1", "BTC", "long", "0-25", "high", "none")
    scorecard_slice = ExpertScorecardSlice(
        expert_id="exp1",
        slice_id=slice_id,
        slice_dimensions={
            "symbol": "BTC",
            "side": "long",
            "distance_bucket": "0-25",
            "confidence_bucket": "high",
        },
        sample_count=10,
        touch_count=5,
        touch_probability=0.5,
        liquidation_match_count=2,
        liquidation_match_probability_given_touch=0.4,
        mfe_quantiles={"p50": 10},
        mae_quantiles={"p50": 5},
        time_to_touch_quantiles={"p50": 100},
        time_to_liquidation_confirm_quantiles={"p50": 200},
        low_sample_flag=False,
        bucket_boundaries={"distance_bps": [0, 25, 50], "confidence": [0.0, 0.5, 1.0]},
    )

    assert scorecard_slice.bucket_boundaries is not None
    assert scorecard_slice.bucket_boundaries["distance_bps"] == [0, 25, 50]


def test_quantile_bucket_set_model() -> None:
    bucket_set = QuantileBucketSet(
        metric_name="distance_bps",
        n_buckets=4,
        boundaries=[0.0, 25.0, 50.0, 75.0, 100.0],
        labels=["q1", "q2", "q3", "q4"],
        observation_count=1000,
    )
    assert bucket_set.metric_name == "distance_bps"
    assert bucket_set.n_buckets == 4
    assert len(bucket_set.boundaries) == 5
    assert len(bucket_set.labels) == 4
    assert bucket_set.observation_count == 1000


def test_quantile_bucket_set_rejects_invalid_contract() -> None:
    with pytest.raises(ValidationError):
        QuantileBucketSet(
            metric_name="distance_bps",
            n_buckets=4,
            boundaries=[0.0, 25.0, 50.0],
            labels=["q1", "q2", "q3", "q4"],
            observation_count=1000,
        )

    with pytest.raises(ValidationError):
        QuantileBucketSet(
            metric_name="distance_bps",
            n_buckets=2,
            boundaries=[50.0, 25.0, 100.0],
            labels=["q1", "q2"],
            observation_count=1000,
        )


def test_bootstrap_dominance_result_model() -> None:
    result = BootstrapDominanceResult(
        expert_a="v1",
        expert_b="v2",
        metric="touch_probability",
        p_a_better=0.85,
        significant=False,
        ci_lower=0.45,
        ci_upper=0.95,
        n_bootstrap=1000,
    )

    assert result.expert_a == "v1"
    assert result.expert_b == "v2"
    assert result.metric == "touch_probability"
    assert result.p_a_better == 0.85
    assert result.significant is False
    assert result.ci_lower == 0.45
    assert result.ci_upper == 0.95
    assert result.n_bootstrap == 1000


def test_bootstrap_dominance_result_rejects_invalid_bounds() -> None:
    with pytest.raises(ValidationError):
        BootstrapDominanceResult(
            expert_a="v1",
            expert_b="v2",
            metric="touch_probability",
            p_a_better=1.2,
            significant=False,
            ci_lower=0.45,
            ci_upper=0.95,
            n_bootstrap=1000,
        )

    with pytest.raises(ValidationError):
        BootstrapDominanceResult(
            expert_a="v1",
            expert_b="v2",
            metric="touch_probability",
            p_a_better=0.60,
            significant=False,
            ci_lower=0.70,
            ci_upper=0.95,
            n_bootstrap=1000,
        )
