from datetime import datetime, timezone

import pytest

from src.liquidationheatmap.models.scorecard import TOUCH_WINDOW_HOURS, ExpertSignalObservation
from src.liquidationheatmap.scorecard.builder import ScorecardBuilder


@pytest.fixture
def sample_expert_artifact():
    return {
        "expert_id": "v1",
        "symbol": "BTCUSDT",
        "snapshot_ts": "2023-11-14T22:13:20Z",
        "reference_price": 60000.0,
        "bucket_grid": {
            "min_price": 59000.0,
            "max_price": 61000.0,
            "step": 1000.0,
            "price_levels": [59000.0, 59500.0, 60500.0, 61000.0],
        },
        "long_distribution": {
            "59000.0": 800.0,
            "59500.0": 400.0,
        },
        "short_distribution": {
            "60500.0": 200.0,
            "61000.0": 600.0,
        },
    }


def test_extract_observations_from_artifact(sample_expert_artifact):
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)

    assert len(observations) == 4
    assert all(isinstance(obs, ExpertSignalObservation) for obs in observations)

    obs1 = next(o for o in observations if o.side == "long" and o.level_price == 59000.0)
    assert obs1.expert_id == "v1"
    assert obs1.level_price == 59000.0
    assert obs1.reference_price == 60000.0
    assert obs1.distance_bps == 167
    assert obs1.confidence == 1.0
    assert obs1.snapshot_ts == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_preserve_untouched_observations(sample_expert_artifact):
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)
    price_path = []

    updated_obs = builder.apply_touch_detection(observations, price_path)

    assert len(updated_obs) == 4
    assert all(obs.touched is False for obs in updated_obs)
    assert all(obs.touch_ts is None for obs in updated_obs)


def test_touch_detection_first_touch_semantics(sample_expert_artifact):
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)

    price_path = [
        {"timestamp": 1700000100, "price": 59500.0},
        {"timestamp": 1700000500, "price": 59010.0},
        {"timestamp": 1700001000, "price": 59000.0},
    ]

    updated_obs = builder.apply_touch_detection(observations, price_path)

    long_obs = next(o for o in updated_obs if o.side == "long" and o.level_price == 59000.0)
    assert long_obs.touched is True
    assert int(long_obs.touch_ts.timestamp()) == 1700000500
    assert long_obs.time_to_touch_secs == 500


def test_touch_detection_outside_window(sample_expert_artifact):
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)

    price_path = [
        {"timestamp": 1700000000 + 15000, "price": 59010.0},
    ]

    updated_obs = builder.apply_touch_detection(observations, price_path)
    long_obs = next(o for o in updated_obs if o.side == "long" and o.level_price == 59000.0)
    assert long_obs.touched is False
    assert long_obs.touch_ts is None


def test_touch_detection_sorts_unsorted_price_path(sample_expert_artifact):
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)

    price_path = [
        {"timestamp": 1700000000 + (TOUCH_WINDOW_HOURS * 3600) + 60, "price": 59005.0},
        {"timestamp": 1700000300, "price": 59020.0},
    ]

    updated_obs = builder.apply_touch_detection(observations, price_path)
    long_obs = next(o for o in updated_obs if o.side == "long" and o.level_price == 59000.0)
    assert long_obs.touched is True
    assert int(long_obs.touch_ts.timestamp()) == 1700000300
    assert long_obs.time_to_touch_secs == 300


def test_post_touch_path_long_side(sample_expert_artifact):
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)

    # Touch at 59000.0 long
    price_path = [
        {"timestamp": 1700000100, "price": 59000.0},  # touch
        {"timestamp": 1700000200, "price": 59050.0},  # favorable +50
        {"timestamp": 1700000300, "price": 58970.0},  # adverse -30
        {"timestamp": 1700000400, "price": 59080.0},  # favorable +80 (MFE)
    ]

    touched_obs = builder.apply_touch_detection(observations, price_path)
    result = builder.apply_post_touch_path(touched_obs, price_path)

    long_obs = next(o for o in result if o.side == "long" and o.level_price == 59000.0)
    assert long_obs.mfe_bps == round(80.0 / 59000.0 * 10000)  # ~14 bps
    assert long_obs.mae_bps == round(30.0 / 59000.0 * 10000)  # ~5 bps


def test_post_touch_path_short_side(sample_expert_artifact):
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)

    # Touch at 61000.0 short
    price_path = [
        {"timestamp": 1700000100, "price": 61000.0},  # touch
        {"timestamp": 1700000200, "price": 60900.0},  # favorable -100 (MFE)
        {"timestamp": 1700000300, "price": 61050.0},  # adverse +50
    ]

    touched_obs = builder.apply_touch_detection(observations, price_path)
    result = builder.apply_post_touch_path(touched_obs, price_path)

    short_obs = next(o for o in result if o.side == "short" and o.level_price == 61000.0)
    assert short_obs.mfe_bps == round(100.0 / 61000.0 * 10000)  # ~16 bps
    assert short_obs.mae_bps == round(50.0 / 61000.0 * 10000)  # ~8 bps


def test_post_touch_path_untouched_remains_null(sample_expert_artifact):
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)

    # No price near any level
    price_path = [{"timestamp": 1700000100, "price": 60000.0}]

    touched_obs = builder.apply_touch_detection(observations, price_path)
    result = builder.apply_post_touch_path(touched_obs, price_path)

    for obs in result:
        assert obs.touched is False
        assert obs.mfe_bps is None
        assert obs.mae_bps is None


def test_touch_detection_adaptive_band(sample_expert_artifact):
    builder = ScorecardBuilder()
    observations = builder.extract_observations(sample_expert_artifact)

    # Base snapshot TS is 1700000000
    # Let's say long_obs level is 59000.0.
    # A price of 59020.0 is ~3.39 bps away from 59000.0, so 5bps fixed band would touch it.
    # A price of 59050.0 is ~8.47 bps away from 59000.0.
    # With a narrow band (e.g. 5 bps), it should NOT be touched.
    # With a wide band (e.g. 15 bps), it SHOULD be touched.

    price_path = [
        {"timestamp": 1700000100, "price": 59050.0},
    ]

    def narrow_band_fn(path, ts, sym):
        return 5

    def wide_band_fn(path, ts, sym):
        return 15

    updated_obs_narrow = builder.apply_touch_detection(
        [obs.model_copy() for obs in observations], price_path, adaptive_band_fn=narrow_band_fn
    )
    long_obs_narrow = next(
        o for o in updated_obs_narrow if o.side == "long" and o.level_price == 59000.0
    )
    assert long_obs_narrow.touched is False

    updated_obs_wide = builder.apply_touch_detection(
        [obs.model_copy() for obs in observations], price_path, adaptive_band_fn=wide_band_fn
    )
    long_obs_wide = next(
        o for o in updated_obs_wide if o.side == "long" and o.level_price == 59000.0
    )
    assert long_obs_wide.touched is True
    assert long_obs_wide.adaptive_touch_band_bps == 15
