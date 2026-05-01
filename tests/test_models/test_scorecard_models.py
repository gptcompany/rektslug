from datetime import datetime, timezone

import pytest

from src.liquidationheatmap.models.scorecard import (
    LIQ_CONFIRM_WINDOW_MINUTES,
    POST_TOUCH_WINDOW_HOURS,
    TOUCH_TOLERANCE_BPS,
    TOUCH_WINDOW_HOURS,
    ExpertScorecardBundle,
    ExpertScorecardSlice,
    ExpertSignalObservation,
)


def test_constants():
    assert TOUCH_WINDOW_HOURS == 4
    assert LIQ_CONFIRM_WINDOW_MINUTES == 15
    assert POST_TOUCH_WINDOW_HOURS == 1
    assert TOUCH_TOLERANCE_BPS == 5

def test_observation_id_deterministic():
    ts = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    id1 = ExpertSignalObservation.generate_id("v1", "BTCUSDT", ts, 65000.0, "long")
    id2 = ExpertSignalObservation.generate_id("v1", "BTCUSDT", ts, 65000.0, "long")
    id3 = ExpertSignalObservation.generate_id("v3", "BTCUSDT", ts, 65000.0, "long")

    assert id1 == id2
    assert id1 != id3


def test_slice_id_deterministic():
    slice_id = ExpertScorecardSlice.generate_slice_id(
        expert_id="v1",
        symbol="BTCUSDT",
        side="long",
        distance_bucket="0-25",
        confidence_bucket="0.8-1.0",
        regime="high_vol",
    )
    assert slice_id == "v1:BTCUSDT:long:0-25:0.8-1.0:high_vol"


def test_observation_model_validation():
    ts = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    obs = ExpertSignalObservation(
        observation_id=ExpertSignalObservation.generate_id(
            "v1", "BTCUSDT", ts, 65000.0, "long"
        ),
        expert_id="v1",
        symbol="BTCUSDT",
        snapshot_ts=ts,
        level_price=65000.0,
        side="long",
        confidence=0.9,
        reference_price=64900.0,
        distance_bps=15,
        touched=False,
    )
    assert obs.expert_id == "v1"
    assert obs.touched is False
    assert obs.touch_ts is None


def test_observation_model_rejects_mismatched_observation_id():
    ts = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="observation_id"):
        ExpertSignalObservation(
            observation_id="wrong-id",
            expert_id="v1",
            symbol="BTCUSDT",
            snapshot_ts=ts,
            level_price=65000.0,
            side="long",
            confidence=0.9,
            reference_price=64900.0,
            distance_bps=15,
            touched=False,
        )


def test_observation_model_rejects_invalid_probability_domain():
    ts = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    valid_id = ExpertSignalObservation.generate_id("v1", "BTCUSDT", ts, 65000.0, "long")
    with pytest.raises(ValueError):
        ExpertSignalObservation(
            observation_id=valid_id,
            expert_id="v1",
            symbol="BTCUSDT",
            snapshot_ts=ts,
            level_price=65000.0,
            side="long",
            confidence=1.5,
            reference_price=64900.0,
            distance_bps=15,
            touched=False,
        )


def test_slice_model_validation():
    slice_id = ExpertScorecardSlice.generate_slice_id(
        expert_id="v1",
        symbol="BTCUSDT",
        side="long",
        distance_bucket="0-25",
        confidence_bucket="0.8-1.0",
        regime="none",
    )
    slc = ExpertScorecardSlice(
        expert_id="v1",
        slice_id=slice_id,
        slice_dimensions={
            "symbol": "BTCUSDT",
            "side": "long",
            "distance_bucket": "0-25",
            "confidence_bucket": "0.8-1.0",
            "regime": "none",
        },
        sample_count=100,
        touch_count=40,
        touch_probability=0.4,
        liquidation_match_count=20,
        liquidation_match_probability_given_touch=0.5,
        mfe_quantiles={"p50": 10},
        mae_quantiles={"p50": 5},
        time_to_touch_quantiles={"p50": 300},
        time_to_liquidation_confirm_quantiles={"p50": 120},
        low_sample_flag=False,
    )
    assert slc.sample_count == 100


def test_slice_model_rejects_mismatched_slice_id():
    with pytest.raises(ValueError, match="slice_id"):
        ExpertScorecardSlice(
            expert_id="v1",
            slice_id="wrong-slice-id",
            slice_dimensions={
                "symbol": "BTCUSDT",
                "side": "long",
                "distance_bucket": "0-25",
                "confidence_bucket": "0.8-1.0",
                "regime": "none",
            },
            sample_count=100,
            touch_count=40,
            touch_probability=0.4,
            liquidation_match_count=20,
            liquidation_match_probability_given_touch=0.5,
            mfe_quantiles={"p50": 10},
            mae_quantiles={"p50": 5},
            time_to_touch_quantiles={"p50": 300},
            time_to_liquidation_confirm_quantiles={"p50": 120},
            low_sample_flag=False,
        )


def test_bundle_serialization():
    slice_id = ExpertScorecardSlice.generate_slice_id(
        expert_id="v1",
        symbol="BTCUSDT",
        side="long",
        distance_bucket="0-25",
        confidence_bucket="0.8-1.0",
        regime="none",
    )
    slc = ExpertScorecardSlice(
        expert_id="v1",
        slice_id=slice_id,
        slice_dimensions={
            "symbol": "BTCUSDT",
            "side": "long",
            "distance_bucket": "0-25",
            "confidence_bucket": "0.8-1.0",
            "regime": "none",
        },
        sample_count=100,
        touch_count=40,
        touch_probability=0.4,
        liquidation_match_count=20,
        liquidation_match_probability_given_touch=0.5,
        mfe_quantiles={"p50": 10},
        mae_quantiles={"p50": 5},
        time_to_touch_quantiles={"p50": 300},
        time_to_liquidation_confirm_quantiles={"p50": 120},
        low_sample_flag=False,
    )
    bundle = ExpertScorecardBundle(slices=[slc])

    data = bundle.model_dump()
    assert len(data["slices"]) == 1
    assert data["slices"][0]["expert_id"] == "v1"
