"""Observation extraction and touch detection for expert scorecards."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from src.liquidationheatmap.models.scorecard import (
    LIQ_CONFIRM_WINDOW_MINUTES,
    POST_TOUCH_WINDOW_HOURS,
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

    def extract_observations(self, artifact: dict[str, Any]) -> list[ExpertSignalObservation]:
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
                distance_bps = round(abs(level_price - reference_price) / reference_price * 10000)

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
        adaptive_band_fn: Callable[[list[dict[str, Any]], datetime, str], int] | None = None,
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
            if adaptive_band_fn is not None:
                band_bps = adaptive_band_fn(price_path, new_obs.snapshot_ts, new_obs.symbol)
                new_obs.adaptive_touch_band_bps = band_bps
                tolerance = new_obs.level_price * band_bps / 10000.0
            else:
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
                    new_obs.time_to_touch_secs = int(
                        (tick_ts - new_obs.snapshot_ts).total_seconds()
                    )
                    break

            updated_observations.append(new_obs)

        return updated_observations

    def apply_liquidation_confirmation(
        self,
        observations: list[ExpertSignalObservation],
        liquidation_events: list[dict[str, Any]],
        volume_threshold: float | None = None,
        price_path: list[dict[str, Any]] | None = None,
    ) -> list[ExpertSignalObservation]:
        """Apply liquidation confirmation matching inside the configured time window post-touch."""
        updated_observations: list[ExpertSignalObservation] = []
        confirm_window = timedelta(minutes=LIQ_CONFIRM_WINDOW_MINUTES)

        normalized_events = sorted(
            (
                {
                    "timestamp": _coerce_timestamp(event["timestamp"]),
                    "price": float(event["price"]),
                    "symbol": event.get("symbol"),
                    "side": event.get("side"),
                }
                for event in liquidation_events
            ),
            key=lambda event: event["timestamp"],
        )

        if volume_threshold is not None and price_path is not None:
            normalized_ticks = sorted(
                (
                    {
                        "timestamp": _coerce_timestamp(tick["timestamp"]),
                        "volume": float(tick["volume"]) if tick.get("volume") is not None else None,
                    }
                    for tick in price_path
                ),
                key=lambda tick: tick["timestamp"],
            )
        else:
            normalized_ticks = []

        for obs in observations:
            new_obs = obs.model_copy()
            if not new_obs.touched or new_obs.touch_ts is None:
                new_obs.liquidation_confirmed = False
                updated_observations.append(new_obs)
                continue

            tolerance = new_obs.level_price * TOUCH_TOLERANCE_BPS / 10000.0
            lower_bound = new_obs.level_price - tolerance
            upper_bound = new_obs.level_price + tolerance
            confirmed = False

            # If using volume-clock, calculate the timestamp at which the volume threshold is reached
            volume_end_ts = None
            missing_volume_encountered = False

            if volume_threshold is not None and normalized_ticks:
                cumulative_volume = 0.0
                for tick in normalized_ticks:
                    if tick["timestamp"] < new_obs.touch_ts:
                        continue
                    if tick["volume"] is None:
                        missing_volume_encountered = True
                        break
                    cumulative_volume += tick["volume"]
                    if cumulative_volume >= volume_threshold:
                        volume_end_ts = tick["timestamp"]
                        break

            for event in normalized_events:
                event_ts = event["timestamp"]
                event_price = event["price"]
                event_symbol = event["symbol"]
                event_side = event["side"]

                # Use volume_end_ts if available and no missing volume, else fallback to confirm_window
                if (
                    volume_threshold is not None
                    and not missing_volume_encountered
                    and volume_end_ts is not None
                ):
                    if event_ts > volume_end_ts:
                        break
                elif (
                    volume_threshold is not None
                    and not missing_volume_encountered
                    and volume_end_ts is None
                ):
                    # We ran out of price path without hitting threshold, any event after touch is considered?
                    # But normally we cap at available data. We'll just continue and check other conditions.
                    pass
                else:
                    # Legacy time-based mode or fallback
                    if event_ts > new_obs.touch_ts + confirm_window:
                        break

                if event_ts < new_obs.touch_ts:
                    continue
                if event_symbol != new_obs.symbol:
                    continue
                if event_side != new_obs.side:
                    continue

                if lower_bound <= event_price <= upper_bound:
                    confirmed = True
                    new_obs.liquidation_confirmed = True
                    new_obs.liquidation_confirm_ts = event_ts
                    new_obs.time_to_liquidation_confirm_secs = int(
                        (event_ts - new_obs.touch_ts).total_seconds()
                    )
                    break

            if not confirmed:
                new_obs.liquidation_confirmed = False

            updated_observations.append(new_obs)

        return updated_observations

    def apply_post_touch_path(
        self,
        observations: list[ExpertSignalObservation],
        price_path: list[dict[str, Any]],
        volume_threshold: float | None = None,
    ) -> list[ExpertSignalObservation]:
        """Compute MFE and MAE from realized price path after first touch."""
        updated_observations: list[ExpertSignalObservation] = []
        post_touch_window = timedelta(hours=POST_TOUCH_WINDOW_HOURS)
        normalized_ticks = sorted(
            (
                {
                    "timestamp": _coerce_timestamp(tick["timestamp"]),
                    "price": float(tick["price"]),
                    "volume": float(tick["volume"]) if tick.get("volume") is not None else None,
                }
                for tick in price_path
            ),
            key=lambda tick: tick["timestamp"],
        )

        for obs in observations:
            new_obs = obs.model_copy()
            if not new_obs.touched or new_obs.touch_ts is None:
                updated_observations.append(new_obs)
                continue

            max_favorable = 0.0
            max_adverse = 0.0

            cumulative_volume = 0.0
            window_closed_by_volume = False
            missing_volume_encountered = False

            for tick in normalized_ticks:
                tick_ts = tick["timestamp"]
                tick_price = tick["price"]
                tick_vol = tick["volume"]

                if tick_ts < new_obs.touch_ts:
                    continue

                if volume_threshold is not None:
                    # Volume-clock mode
                    if tick_vol is None:
                        missing_volume_encountered = True

                    if not missing_volume_encountered and tick_vol is not None:
                        cumulative_volume += tick_vol

                    # Stop if we hit the threshold
                    if cumulative_volume >= volume_threshold:
                        window_closed_by_volume = True

                        # Process this tick as the closing tick, then break
                        if new_obs.side == "long":
                            favorable = tick_price - new_obs.level_price
                            adverse = new_obs.level_price - tick_price
                        else:
                            favorable = new_obs.level_price - tick_price
                            adverse = tick_price - new_obs.level_price

                        if favorable > max_favorable:
                            max_favorable = favorable
                        if adverse > max_adverse:
                            max_adverse = adverse

                        break

                    # If we don't have volume data, or haven't hit threshold,
                    # we still process the tick until we run out of data
                    # (since we don't stop on time in volume mode, unless fallback applies)

                    # Wait, the spec says: "Time-based metrics may still be emitted as secondary metadata if the price path has timestamps."
                    # If missing volume data, we fallback to time window?
                    # T027 text: "implement missing-volume fallback in apply_post_touch_path()" -> fallback to legacy time window.
                    if (
                        missing_volume_encountered
                        and tick_ts > new_obs.touch_ts + post_touch_window
                    ):
                        break
                else:
                    # Legacy time-based mode
                    if tick_ts > new_obs.touch_ts + post_touch_window:
                        break

                if new_obs.side == "long":
                    favorable = tick_price - new_obs.level_price
                    adverse = new_obs.level_price - tick_price
                else:
                    favorable = new_obs.level_price - tick_price
                    adverse = tick_price - new_obs.level_price

                if favorable > max_favorable:
                    max_favorable = favorable
                if adverse > max_adverse:
                    max_adverse = adverse

            new_obs.mfe_bps = round(max_favorable / new_obs.level_price * 10000)
            new_obs.mae_bps = round(max_adverse / new_obs.level_price * 10000)

            if volume_threshold is not None:
                if missing_volume_encountered:
                    new_obs.volume_window_complete = None
                else:
                    new_obs.volume_window_complete = window_closed_by_volume
                new_obs.post_touch_volume = (
                    cumulative_volume if not missing_volume_encountered else None
                )

            updated_observations.append(new_obs)

        return updated_observations

    def build_coverage_metadata(
        self,
        expected_experts: list[str],
        available_artifacts: list[dict[str, Any]],
        liquidation_stream_available: bool,
    ) -> dict[str, Any]:
        """Build coverage metadata for missing artifacts and missing streams."""
        available_set = set(
            (
                artifact["expert_id"],
                _coerce_timestamp(
                    artifact["snapshot_ts"] if "snapshot_ts" in artifact else artifact["timestamp"]
                ),
            )
            for artifact in available_artifacts
        )

        unique_timestamps = sorted(list(set(ts for _, ts in available_set)))

        missing_artifacts = []
        for ts in unique_timestamps:
            for expert in expected_experts:
                if (expert, ts) not in available_set:
                    missing_artifacts.append(
                        {
                            "expert_id": expert,
                            "snapshot_ts": ts.isoformat().replace("+00:00", "Z"),
                        }
                    )

        return {
            "missing_artifacts": missing_artifacts,
            "liquidation_stream_available": liquidation_stream_available,
        }
