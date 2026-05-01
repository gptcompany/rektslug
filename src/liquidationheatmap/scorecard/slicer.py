from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict
from src.liquidationheatmap.models.scorecard import ExpertSignalObservation, ExpertScorecardSlice

class ScorecardSlicer:
    def __init__(self, regime_map: Optional[Dict[datetime, str]] = None):
        self.regime_map = regime_map or {}
        
    def _get_distance_bucket(self, distance_bps: int) -> str:
        if distance_bps <= 25:
            return "0-25"
        elif distance_bps <= 50:
            return "25-50"
        elif distance_bps <= 100:
            return "50-100"
        elif distance_bps <= 200:
            return "100-200"
        else:
            return "200+"
            
    def _get_confidence_bucket(self, confidence: float) -> str:
        if confidence <= 0.3:
            return "0.0-0.3"
        elif confidence <= 0.6:
            return "0.3-0.6"
        elif confidence <= 0.8:
            return "0.6-0.8"
        else:
            return "0.8-1.0"

    def slice_observations(
        self, observations: List[ExpertSignalObservation]
    ) -> Dict[str, List[ExpertSignalObservation]]:
        """Groups observations into slices based on dimensions."""
        slices = defaultdict(list)
        
        for obs in observations:
            dist_bucket = self._get_distance_bucket(obs.distance_bps)
            conf_bucket = self._get_confidence_bucket(obs.confidence)
            regime = self.regime_map.get(obs.snapshot_ts, "none")
            
            slice_id = ExpertScorecardSlice.generate_slice_id(
                expert_id=obs.expert_id,
                symbol=obs.symbol,
                side=obs.side,
                distance_bucket=dist_bucket,
                confidence_bucket=conf_bucket,
                regime=regime,
            )
            
            slices[slice_id].append(obs)
            
        return dict(slices)
