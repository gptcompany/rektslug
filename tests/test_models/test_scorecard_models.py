import pytest
from src.liquidationheatmap.models.scorecard import (
    ExpertSignalObservation,
    ExpertScorecardSlice,
    ExpertScorecardBundle,
    TOUCH_WINDOW_HOURS,
    LIQ_CONFIRM_WINDOW_MINUTES,
    POST_TOUCH_WINDOW_HOURS,
    TOUCH_TOLERANCE_BPS,
)

def test_constants():
    assert TOUCH_WINDOW_HOURS == 4
    assert LIQ_CONFIRM_WINDOW_MINUTES == 15
    assert POST_TOUCH_WINDOW_HOURS == 1
    assert TOUCH_TOLERANCE_BPS == 5

def test_observation_id_deterministic():
    id1 = ExpertSignalObservation.generate_id("v1", "BTC-USD", 1700000000, 65000.0, "long")
    id2 = ExpertSignalObservation.generate_id("v1", "BTC-USD", 1700000000, 65000.0, "long")
    id3 = ExpertSignalObservation.generate_id("v3", "BTC-USD", 1700000000, 65000.0, "long")
    
    assert id1 == id2
    assert id1 != id3

def test_slice_id_deterministic():
    slice_id = ExpertScorecardSlice.generate_slice_id(
        expert_id="v1",
        symbol="BTC-USD",
        side="long",
        distance_bucket="0-25",
        confidence_bucket="0.8-1.0",
        regime="high_vol"
    )
    assert slice_id == "v1:BTC-USD:long:0-25:0.8-1.0:high_vol"

def test_observation_model_validation():
    # Test required fields
    obs = ExpertSignalObservation(
        observation_id="test_id",
        expert_id="v1",
        symbol="BTC-USD",
        snapshot_ts=1700000000,
        level_price=65000.0,
        side="long",
        confidence=0.9,
        reference_price=64900.0,
        distance_bps=15,
        touched=False
    )
    assert obs.expert_id == "v1"
    assert obs.touched is False
    assert obs.touch_ts is None

def test_slice_model_validation():
    slc = ExpertScorecardSlice(
        expert_id="v1",
        slice_id="test_slice",
        slice_dimensions={"symbol": "BTC"},
        sample_count=100,
        touch_count=40,
        touch_probability=0.4,
        liquidation_match_count=20,
        liquidation_match_probability_given_touch=0.5,
        mfe_quantiles={"p50": 10},
        mae_quantiles={"p50": 5},
        time_to_touch_quantiles={"p50": 300},
        low_sample_flag=False
    )
    assert slc.sample_count == 100

def test_bundle_serialization():
    slc = ExpertScorecardSlice(
        expert_id="v1",
        slice_id="test_slice",
        slice_dimensions={"symbol": "BTC"},
        sample_count=100,
        touch_count=40,
        touch_probability=0.4,
        liquidation_match_count=20,
        liquidation_match_probability_given_touch=0.5,
        mfe_quantiles={"p50": 10},
        mae_quantiles={"p50": 5},
        time_to_touch_quantiles={"p50": 300},
        low_sample_flag=False
    )
    bundle = ExpertScorecardBundle(slices=[slc])
    
    # Check serialization
    data = bundle.model_dump()
    assert len(data["slices"]) == 1
    assert data["slices"][0]["expert_id"] == "v1"
