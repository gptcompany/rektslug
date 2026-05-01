from typing import List, Dict, Any, Optional
import numpy as np
from src.liquidationheatmap.models.scorecard import ExpertSignalObservation

def _compute_quantiles(values: List[int]) -> Dict[str, int]:
    if not values:
        return {"p10": 0, "p25": 0, "p50": 0, "p75": 0, "p90": 0}
    return {
        "p10": int(np.percentile(values, 10)),
        "p25": int(np.percentile(values, 25)),
        "p50": int(np.percentile(values, 50)),
        "p75": int(np.percentile(values, 75)),
        "p90": int(np.percentile(values, 90)),
    }

class ScorecardAggregator:
    def __init__(self, min_samples: int = 30):
        self.min_samples = min_samples
        
    def aggregate_probabilities(self, observations: List[ExpertSignalObservation]) -> Dict[str, Any]:
        sample_count = len(observations)
        touch_count = sum(1 for obs in observations if obs.touched)
        
        touch_probability = touch_count / sample_count if sample_count > 0 else 0.0
        
        liquidation_match_count = sum(1 for obs in observations if obs.liquidation_confirmed)
        liquidation_match_probability = (
            liquidation_match_count / touch_count if touch_count > 0 else 0.0
        )
        
        return {
            "sample_count": sample_count,
            "touch_count": touch_count,
            "touch_probability": round(touch_probability, 6),
            "liquidation_match_count": liquidation_match_count,
            "liquidation_match_probability_given_touch": round(liquidation_match_probability, 6),
            "low_sample_flag": sample_count < self.min_samples,
        }
        
    def aggregate_quantiles(self, observations: List[ExpertSignalObservation]) -> Dict[str, Any]:
        mfe_values = [obs.mfe_bps for obs in observations if obs.mfe_bps is not None]
        mae_values = [obs.mae_bps for obs in observations if obs.mae_bps is not None]
        time_to_touch_values = [obs.time_to_touch_secs for obs in observations if obs.time_to_touch_secs is not None]
        time_to_liq_values = [
            obs.time_to_liquidation_confirm_secs 
            for obs in observations 
            if obs.time_to_liquidation_confirm_secs is not None
        ]
        
        return {
            "mfe_quantiles": _compute_quantiles(mfe_values),
            "mae_quantiles": _compute_quantiles(mae_values),
            "time_to_touch_quantiles": _compute_quantiles(time_to_touch_values),
            "time_to_liquidation_confirm_quantiles": _compute_quantiles(time_to_liq_values),
        }
