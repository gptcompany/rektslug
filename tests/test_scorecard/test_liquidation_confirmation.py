import pytest
from datetime import datetime, timezone, timedelta
from src.liquidationheatmap.models.scorecard import ExpertSignalObservation
from src.liquidationheatmap.scorecard.builder import ScorecardBuilder

@pytest.fixture
def touched_observation():
    snapshot_ts = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    obs_id = ExpertSignalObservation.generate_id(
        expert_id="v1",
        symbol="BTC-USD",
        snapshot_ts=snapshot_ts,
        level_price=59000.0,
        side="long"
    )
    obs = ExpertSignalObservation(
        observation_id=obs_id,
        expert_id="v1",
        symbol="BTC-USD",
        snapshot_ts=snapshot_ts,
        level_price=59000.0,
        side="long",
        confidence=0.8,
        reference_price=60000.0,
        distance_bps=166,
        touched=True,
        touch_ts=datetime(2023, 1, 1, 13, 0, tzinfo=timezone.utc),
        time_to_touch_secs=3600
    )
    return obs

def test_liquidation_confirmation_matching(touched_observation):
    builder = ScorecardBuilder()
    obs_list = [touched_observation]
    
    # Provide liquidation events
    liquidation_events = [
        {"timestamp": datetime(2023, 1, 1, 12, 30, tzinfo=timezone.utc).timestamp(), "price": 59000.0, "side": "long"}, # Before touch
        {"timestamp": datetime(2023, 1, 1, 13, 5, tzinfo=timezone.utc).timestamp(), "price": 59010.0, "side": "long"},  # After touch, inside window
        {"timestamp": datetime(2023, 1, 1, 14, 0, tzinfo=timezone.utc).timestamp(), "price": 59000.0, "side": "long"}   # After touch, outside 15m window
    ]
    
    updated_obs = builder.apply_liquidation_confirmation(obs_list, liquidation_events)
    
    assert len(updated_obs) == 1
    assert updated_obs[0].liquidation_confirmed is True
    assert int(updated_obs[0].liquidation_confirm_ts.timestamp()) == int(datetime(2023, 1, 1, 13, 5, tzinfo=timezone.utc).timestamp())
    assert updated_obs[0].time_to_liquidation_confirm_secs == 300

def test_liquidation_confirmation_source_frozen():
    from src.liquidationheatmap.models.scorecard import LIQUIDATION_CONFIRMATION_SOURCE
    assert LIQUIDATION_CONFIRMATION_SOURCE is not None
    assert "liquidations" in LIQUIDATION_CONFIRMATION_SOURCE.lower()

def test_coverage_metadata():
    builder = ScorecardBuilder()
    
    # Suppose we pass missing artifacts for certain timestamps or experts
    metadata = builder.build_coverage_metadata(
        expected_experts=["v1", "v3", "v4", "v5"],
        available_artifacts=[
            {"expert_id": "v1", "timestamp": 1700000000},
            {"expert_id": "v3", "timestamp": 1700000000}
            # v4, v5 missing
        ],
        liquidation_stream_available=False
    )
    
    assert metadata["missing_artifacts"] == [
        {"expert_id": "v4", "timestamp": 1700000000},
        {"expert_id": "v5", "timestamp": 1700000000}
    ]
    assert metadata["liquidation_stream_available"] is False
