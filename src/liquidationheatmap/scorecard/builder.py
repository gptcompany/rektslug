"""Observation extraction and touch detection for expert scorecards."""

from datetime import datetime, timedelta, timezone
from typing import Any

from src.liquidationheatmap.models.scorecard import (
    TOUCH_TOLERANCE_BPS,
    TOUCH_WINDOW_HOURS,
    ExpertSignalObservation,
)


def _coerce_timestamp(value: Any) -> datetime:
    """Normalize supported timestamp shapes to timezone-aware UTC datetimes."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"Unsupported timestamp value: {value!r}")


class ScorecardBuilder:
    """Build scorecard observations from retained expert artifacts."""

    def extract_observations(
        self, artifact: dict[str, Any]
    ) -> list[ExpertSignalObservation]:
        """Extract one observation per price level from the retained artifact contract."""
        observations: list[ExpertSignalObservation] = []
        expert_id = artifact["expert_id"]
        symbol = artifact["symbol"]
        snapshot_ts = _coerce_timestamp(artifact["snapshot_ts"])
        reference_price = artifact["reference_price"]

        distributions = (
            ("long", artifact.get("long_distribution", {})),
            ("short", artifact.get("short_distribution", {})),
        )
        for side, distribution in distributions:
            numeric_values = [float(volume) for volume in distribution.values()]
            max_volume = max(numeric_values, default=1.0)
            if max_volume <= 0:
                max_volume = 1.0

            for price_str, volume in distribution.items():
                level_price = float(price_str)
                confidence = round(min(max(float(volume) / max_volume, 0.0), 1.0), 6)
                distance_bps = round(
                    abs(level_price - reference_price) / reference_price * 10000
                )

                obs_id = ExpertSignalObservation.generate_id(
                    expert_id=expert_id,
                    symbol=symbol,
                    snapshot_ts=snapshot_ts,
                    level_price=level_price,
                    side=side,
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
                    touched=False,
                )
                observations.append(obs)

        return observations

    def apply_touch_detection(
        self,
        observations: list[ExpertSignalObservation],
        price_path: list[dict[str, Any]],
    ) -> list[ExpertSignalObservation]:
        """Apply first-touch semantics inside the configured time window."""
        updated_observations: list[ExpertSignalObservation] = []
        touch_window = timedelta(hours=TOUCH_WINDOW_HOURS)
        normalized_ticks = sorted(
            (
                {
                    "timestamp": _coerce_timestamp(tick["timestamp"]),
                    "price": float(tick["price"]),
                }
                for tick in price_path
            ),
            key=lambda tick: tick["timestamp"],
        )

        for obs in observations:
            new_obs = obs.model_copy()
            tolerance = new_obs.level_price * TOUCH_TOLERANCE_BPS / 10000.0
            lower_bound = new_obs.level_price - tolerance
            upper_bound = new_obs.level_price + tolerance

            for tick in normalized_ticks:
                tick_ts = tick["timestamp"]
                tick_price = tick["price"]

                if tick_ts > new_obs.snapshot_ts + touch_window:
                    break
                if tick_ts < new_obs.snapshot_ts:
                    continue

                if lower_bound <= tick_price <= upper_bound:
                    new_obs.touched = True
                    new_obs.touch_ts = tick_ts
                    new_obs.time_to_touch_secs = int((tick_ts - new_obs.snapshot_ts).total_seconds())
                    break

            updated_observations.append(new_obs)

        return updated_observations
