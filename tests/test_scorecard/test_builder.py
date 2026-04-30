import pytest
from datetime import datetime, timezone
from src.liquidationheatmap.models.scorecard import ExpertSignalObservation, TOUCH_WINDOW_HOURS
from src.liquidationheatmap.scorecard.builder import ScorecardBuilder

@pytest.fixture
def sample_expert_artifact():
    return {
        "expert_id": "v1",
        "symbol": "BTC-USD",
        "timestamp": 1700000000,
        "reference_price": 60000.0,
        "levels": [
            {"price": 59000.0, "side": "long", "confidence": 0.8},
            {"price": 61000.0, "side": "short", "confidence": 0.6},
        ]
    }

def test_extract_observations_from_artifact(sample_expert_artifact):
    # T006R: failing test for observation extraction
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)
    
    assert len(observations) == 2
    assert all(isinstance(obs, ExpertSignalObservation) for obs in observations)
    
    obs1 = next(o for o in observations if o.side == "long")
    assert obs1.expert_id == "v1"
    assert obs1.level_price == 59000.0
    assert obs1.reference_price == 60000.0
    assert obs1.distance_bps == 166  # roughly (60000-59000)/60000 * 10000

def test_preserve_untouched_observations(sample_expert_artifact):
    # T007b: failing test that touched=false are preserved
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)
    
    # Provide an empty price path
    price_path = []
    
    updated_obs = builder.apply_touch_detection(observations, price_path)
    
    assert len(updated_obs) == 2
    assert all(obs.touched is False for obs in updated_obs)
    assert all(obs.touch_ts is None for obs in updated_obs)

def test_touch_detection_first_touch_semantics(sample_expert_artifact):
    # T008R: failing test for touch detection with first-touch semantics
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)
    
    # 59000.0 long is at distance 166 bps. Tolerance is 5 bps. 59000 * 0.0005 = 29.5
    # So bounds are [58970.5, 59029.5]
    
    price_path = [
        {"timestamp": 1700000100, "price": 59500.0},
        {"timestamp": 1700000500, "price": 59010.0},  # First touch!
        {"timestamp": 1700001000, "price": 59000.0},  # Second touch
    ]
    
    updated_obs = builder.apply_touch_detection(observations, price_path)
    
    long_obs = next(o for o in updated_obs if o.side == "long")
    assert long_obs.touched is True
    assert int(long_obs.touch_ts.timestamp()) == 1700000500  # Must be first touch
    assert long_obs.time_to_touch_secs == 500

def test_touch_detection_outside_window(sample_expert_artifact):
    # Touch happens outside the 4h window
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)
    
    # 4 hours = 14400 seconds
    price_path = [
        {"timestamp": 1700000000 + 15000, "price": 59010.0},  # Late touch
    ]
    
    updated_obs = builder.apply_touch_detection(observations, price_path)
    long_obs = next(o for o in updated_obs if o.side == "long")
    assert long_obs.touched is False
    assert long_obs.touch_ts is None
