import pytest
from datetime import datetime, timezone
from src.liquidationheatmap.models.scorecard import ExpertSignalObservation
from src.liquidationheatmap.scorecard.slicer import ScorecardSlicer

@pytest.fixture
def observations():
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    obs_list = []
    
    # Obs 1: v1, long, dist 10, conf 0.9 -> dist bucket: 0-25, conf bucket: 0.8-1.0
    id1 = ExpertSignalObservation.generate_id("v1", "BTC-USD", base_time, 59000.0, "long")
    obs_list.append(ExpertSignalObservation(
        observation_id=id1, expert_id="v1", symbol="BTC-USD", snapshot_ts=base_time,
        level_price=59000.0, side="long", confidence=0.9, reference_price=60000.0, distance_bps=10,
        touched=True, touch_ts=base_time, liquidation_confirmed=False
    ))
    
    # Obs 2: v1, long, dist 20, conf 0.85 -> dist bucket: 0-25, conf bucket: 0.8-1.0 (Same slice as Obs 1)
    id2 = ExpertSignalObservation.generate_id("v1", "BTC-USD", base_time, 58000.0, "long")
    obs_list.append(ExpertSignalObservation(
        observation_id=id2, expert_id="v1", symbol="BTC-USD", snapshot_ts=base_time,
        level_price=58000.0, side="long", confidence=0.85, reference_price=60000.0, distance_bps=20,
        touched=False
    ))
    
    # Obs 3: v1, short, dist 60, conf 0.5 -> dist bucket: 50-100, conf bucket: 0.3-0.6
    id3 = ExpertSignalObservation.generate_id("v1", "BTC-USD", base_time, 61000.0, "short")
    obs_list.append(ExpertSignalObservation(
        observation_id=id3, expert_id="v1", symbol="BTC-USD", snapshot_ts=base_time,
        level_price=61000.0, side="short", confidence=0.5, reference_price=60000.0, distance_bps=60,
        touched=False
    ))

    # Obs 4: v3, long, dist 300, conf 0.1 -> dist bucket: 200+, conf bucket: 0.0-0.3
    id4 = ExpertSignalObservation.generate_id("v3", "BTC-USD", base_time, 50000.0, "long")
    obs_list.append(ExpertSignalObservation(
        observation_id=id4, expert_id="v3", symbol="BTC-USD", snapshot_ts=base_time,
        level_price=50000.0, side="long", confidence=0.1, reference_price=60000.0, distance_bps=300,
        touched=False
    ))
    
    return obs_list

def test_slicing_observations(observations):
    slicer = ScorecardSlicer()
    
    # T017R: failing tests for slice aggregation by symbol, side, distance bucket, confidence bucket
    slices = slicer.slice_observations(observations)
    
    assert len(slices) == 3
    
    # Find the slice for v1, long, 0-25, 0.8-1.0
    slice1 = slices["v1:BTC-USD:long:0-25:0.8-1.0:none"]
    assert len(slice1) == 2
    
    slice2 = slices["v1:BTC-USD:short:50-100:0.3-0.6:none"]
    assert len(slice2) == 1
    
    slice3 = slices["v3:BTC-USD:long:200+:0.0-0.3:none"]
    assert len(slice3) == 1

def test_volatility_regime_slicing(observations):
    # Add a mock regime map mapping snapshot_ts to regime
    slicer = ScorecardSlicer(regime_map={observations[0].snapshot_ts: "high_vol"})
    slices = slicer.slice_observations(observations)
    
    assert "v1:BTC-USD:long:0-25:0.8-1.0:high_vol" in slices
