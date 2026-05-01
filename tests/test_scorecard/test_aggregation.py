import pytest
from datetime import datetime, timezone
from src.liquidationheatmap.models.scorecard import ExpertSignalObservation
from src.liquidationheatmap.scorecard.aggregator import ScorecardAggregator

@pytest.fixture
def sample_observations():
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    obs_list = []
    
    # 4 observations total. 3 touched, 1 untouched.
    # Of the 3 touched, 2 are liquidation_confirmed.
    
    # Obs 1: touched, confirmed
    obs1_id = ExpertSignalObservation.generate_id("v1", "BTC-USD", base_time, 59000.0, "long")
    obs_list.append(ExpertSignalObservation(
        observation_id=obs1_id, expert_id="v1", symbol="BTC-USD", snapshot_ts=base_time,
        level_price=59000.0, side="long", confidence=0.8, reference_price=60000.0, distance_bps=166,
        touched=True, touch_ts=datetime(2023, 1, 1, 12, 30, tzinfo=timezone.utc),
        liquidation_confirmed=True, liquidation_confirm_ts=datetime(2023, 1, 1, 12, 35, tzinfo=timezone.utc),
        mfe_bps=50, mae_bps=10, time_to_touch_secs=1800, time_to_liquidation_confirm_secs=300
    ))
    
    # Obs 2: touched, confirmed
    obs2_id = ExpertSignalObservation.generate_id("v1", "BTC-USD", base_time, 58000.0, "long")
    obs_list.append(ExpertSignalObservation(
        observation_id=obs2_id, expert_id="v1", symbol="BTC-USD", snapshot_ts=base_time,
        level_price=58000.0, side="long", confidence=0.9, reference_price=60000.0, distance_bps=333,
        touched=True, touch_ts=datetime(2023, 1, 1, 13, 0, tzinfo=timezone.utc),
        liquidation_confirmed=True, liquidation_confirm_ts=datetime(2023, 1, 1, 13, 10, tzinfo=timezone.utc),
        mfe_bps=100, mae_bps=20, time_to_touch_secs=3600, time_to_liquidation_confirm_secs=600
    ))
    
    # Obs 3: touched, not confirmed
    obs3_id = ExpertSignalObservation.generate_id("v1", "BTC-USD", base_time, 57000.0, "long")
    obs_list.append(ExpertSignalObservation(
        observation_id=obs3_id, expert_id="v1", symbol="BTC-USD", snapshot_ts=base_time,
        level_price=57000.0, side="long", confidence=0.7, reference_price=60000.0, distance_bps=500,
        touched=True, touch_ts=datetime(2023, 1, 1, 14, 0, tzinfo=timezone.utc),
        liquidation_confirmed=False, liquidation_confirm_ts=None,
        mfe_bps=10, mae_bps=50, time_to_touch_secs=7200, time_to_liquidation_confirm_secs=None
    ))
    
    # Obs 4: not touched
    obs4_id = ExpertSignalObservation.generate_id("v1", "BTC-USD", base_time, 56000.0, "long")
    obs_list.append(ExpertSignalObservation(
        observation_id=obs4_id, expert_id="v1", symbol="BTC-USD", snapshot_ts=base_time,
        level_price=56000.0, side="long", confidence=0.5, reference_price=60000.0, distance_bps=666,
        touched=False, touch_ts=None, liquidation_confirmed=None, liquidation_confirm_ts=None,
        mfe_bps=None, mae_bps=None, time_to_touch_secs=None, time_to_liquidation_confirm_secs=None
    ))
    
    return obs_list

def test_empirical_probability_aggregation(sample_observations):
    aggregator = ScorecardAggregator()
    
    # T012R: failing tests for empirical probability aggregation
    result = aggregator.aggregate_probabilities(sample_observations)
    
    assert result["sample_count"] == 4
    assert result["touch_count"] == 3
    assert result["touch_probability"] == 0.75  # 3/4
    assert result["liquidation_match_count"] == 2
    assert result["liquidation_match_probability_given_touch"] == pytest.approx(0.6666, 0.001)  # 2/3

def test_quantile_aggregation(sample_observations):
    aggregator = ScorecardAggregator()
    
    # T014R: failing tests for MFE, MAE, and time-to-event quantiles
    result = aggregator.aggregate_quantiles(sample_observations)
    
    mfe_q = result["mfe_quantiles"]
    assert mfe_q["p50"] == 50
    assert mfe_q["p90"] == 90
    
    mae_q = result["mae_quantiles"]
    assert mae_q["p50"] == 20
    
    t2t_q = result["time_to_touch_quantiles"]
    assert t2t_q["p50"] == 3600
    
    # 2 confirmed liquidations
    t2l_q = result["time_to_liquidation_confirm_quantiles"]
    assert t2l_q["p50"] == 450  # average of 300 and 600

def test_low_sample_flag():
    aggregator = ScorecardAggregator(min_samples=10)
    
    # With only 4 samples, it should trigger low sample flag
    result = aggregator.aggregate_probabilities([])
    assert result["sample_count"] == 0
    assert result["low_sample_flag"] is True
