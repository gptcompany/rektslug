"""Slice observations into deterministic expert comparison buckets."""

from collections import defaultdict
from datetime import datetime
from typing import Optional

from src.liquidationheatmap.models.scorecard import (
    ExpertScorecardSlice,
    ExpertSignalObservation,
)


class ScorecardSlicer:
    """Slice observations into deterministic comparison buckets."""

    def __init__(self, regime_map: Optional[dict[datetime, str]] = None):
        self.regime_map = regime_map or {}

    def _get_distance_bucket(self, distance_bps: int) -> str:
        if distance_bps <= 25:
            return "0-25"
        if distance_bps <= 50:
            return "25-50"
        if distance_bps <= 100:
            return "50-100"
        if distance_bps <= 200:
            return "100-200"
        return "200+"

    def _get_confidence_bucket(self, confidence: float) -> str:
        if confidence <= 0.3:
            return "0.0-0.3"
        if confidence <= 0.6:
            return "0.3-0.6"
        if confidence <= 0.8:
            return "0.6-0.8"
        return "0.8-1.0"

    def get_slice_dimensions(
        self, observation: ExpertSignalObservation
    ) -> dict[str, str]:
        """Derive deterministic slice dimensions for one observation."""
        return {
            "symbol": observation.symbol,
            "side": observation.side,
            "distance_bucket": self._get_distance_bucket(observation.distance_bps),
            "confidence_bucket": self._get_confidence_bucket(observation.confidence),
            "regime": self.regime_map.get(observation.snapshot_ts, "none"),
        }

    def slice_observations(
        self, observations: list[ExpertSignalObservation]
    ) -> dict[str, list[ExpertSignalObservation]]:
        """Group observations into scorecard slices."""
        slices: defaultdict[str, list[ExpertSignalObservation]] = defaultdict(list)

        for observation in observations:
            dimensions = self.get_slice_dimensions(observation)
            slice_id = ExpertScorecardSlice.generate_slice_id(
                expert_id=observation.expert_id,
                symbol=dimensions["symbol"],
                side=dimensions["side"],
                distance_bucket=dimensions["distance_bucket"],
                confidence_bucket=dimensions["confidence_bucket"],
                regime=dimensions["regime"],
            )
            slices[slice_id].append(observation)

        return dict(slices)
