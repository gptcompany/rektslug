import copy
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

from src.liquidationheatmap.models.scorecard import (
    ExpertSignalObservation,
    TOUCH_WINDOW_HOURS,
    TOUCH_TOLERANCE_BPS
)

class ScorecardBuilder:
    def extract_observations(self, artifact: Dict[str, Any]) -> List[ExpertSignalObservation]:
        observations = []
        expert_id = artifact["expert_id"]
        symbol = artifact["symbol"]
        # Convert unix timestamp to UTC datetime
        snapshot_ts = datetime.fromtimestamp(artifact["timestamp"], tz=timezone.utc)
        reference_price = artifact["reference_price"]
        
        for level in artifact.get("levels", []):
            level_price = level["price"]
            side = level["side"]
            confidence = level.get("confidence", 1.0)
            
            distance_bps = int(abs(level_price - reference_price) / reference_price * 10000)
            
            obs_id = ExpertSignalObservation.generate_id(
                expert_id=expert_id,
                symbol=symbol,
                snapshot_ts=snapshot_ts,
                level_price=level_price,
                side=side
            )
            
            obs = ExpertSignalObservation(
                observation_id=obs_id,
                expert_id=expert_id,
                symbol=symbol,
                snapshot_ts=snapshot_ts,
                level_price=level_price,
                side=side,
                confidence=confidence,
                reference_price=reference_price,
                distance_bps=distance_bps,
                touched=False
            )
            observations.append(obs)
            
        return observations
        
    def apply_touch_detection(
        self, observations: List[ExpertSignalObservation], price_path: List[Dict[str, Any]]
    ) -> List[ExpertSignalObservation]:
        updated_observations = []
        touch_window = timedelta(hours=TOUCH_WINDOW_HOURS)
        
        for obs in observations:
            new_obs = obs.model_copy()
            
            tolerance = new_obs.level_price * TOUCH_TOLERANCE_BPS / 10000.0
            lower_bound = new_obs.level_price - tolerance
            upper_bound = new_obs.level_price + tolerance
            
            # Find first touch
            for tick in price_path:
                tick_ts_unix = tick["timestamp"]
                tick_ts = datetime.fromtimestamp(tick_ts_unix, tz=timezone.utc)
                tick_price = tick["price"]
                
                # Check if outside touch window
                if tick_ts > new_obs.snapshot_ts + touch_window:
                    break
                
                # Cannot touch in the past relative to snapshot
                if tick_ts < new_obs.snapshot_ts:
                    continue
                    
                if lower_bound <= tick_price <= upper_bound:
                    new_obs.touched = True
                    new_obs.touch_ts = tick_ts
                    new_obs.time_to_touch_secs = int((tick_ts - new_obs.snapshot_ts).total_seconds())
                    break
                    
            updated_observations.append(new_obs)
            
        return updated_observations
