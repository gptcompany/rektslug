"""Aggregation helpers for empirical expert scorecards."""

from math import ceil, floor
from typing import Any

from src.liquidationheatmap.models.scorecard import ExpertSignalObservation


def _compute_quantiles(values: list[int]) -> dict[str, int]:
    """Compute deterministic linear-interpolated percentiles in integer space."""
    if not values:
        return {"p10": 0, "p25": 0, "p50": 0, "p75": 0, "p90": 0}

    sorted_values = sorted(values)

    def percentile(q: float) -> int:
        if len(sorted_values) == 1:
            return sorted_values[0]
        position = (len(sorted_values) - 1) * q
        lower_index = floor(position)
        upper_index = ceil(position)
        if lower_index == upper_index:
            return sorted_values[lower_index]
        lower_value = sorted_values[lower_index]
        upper_value = sorted_values[upper_index]
        interpolated = lower_value + (upper_value - lower_value) * (position - lower_index)
        return int(round(interpolated))

    return {
        "p10": percentile(0.10),
        "p25": percentile(0.25),
        "p50": percentile(0.50),
        "p75": percentile(0.75),
        "p90": percentile(0.90),
    }


class ScorecardAggregator:
    """Aggregate empirical probabilities and path quantiles."""

    def __init__(self, min_samples: int = 30):
        self.min_samples = min_samples

    def aggregate_probabilities(
        self, observations: list[ExpertSignalObservation]
    ) -> dict[str, Any]:
        sample_count = len(observations)
        touched_observations = [obs for obs in observations if obs.touched]
        touch_count = len(touched_observations)
        liquidation_match_count = sum(
            1 for obs in touched_observations if obs.liquidation_confirmed
        )

        touch_probability = touch_count / sample_count if sample_count > 0 else 0.0
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

    def aggregate_quantiles(
        self, observations: list[ExpertSignalObservation]
    ) -> dict[str, dict[str, int]]:
        mfe_values = [obs.mfe_bps for obs in observations if obs.mfe_bps is not None]
        mae_values = [obs.mae_bps for obs in observations if obs.mae_bps is not None]
        time_to_touch_values = [
            obs.time_to_touch_secs for obs in observations if obs.time_to_touch_secs is not None
        ]
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
