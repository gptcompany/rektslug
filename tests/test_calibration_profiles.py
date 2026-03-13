"""TDD RED: Tests for calibration profile selection and manifest recording.

Spec-018: rektslug-ank calibration profile must be selectable without
breaking the default profile. Reports must record which profile was active.
"""

import pytest


class TestProfileRegistry:
    """Profile registry must expose named profiles with model parameters."""

    def test_default_profile_exists(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-default")
        assert profile is not None
        assert profile.name == "rektslug-default"

    def test_ank_profile_exists(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-ank")
        assert profile is not None
        assert profile.name == "rektslug-ank"

    def test_glass_profile_exists(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-glass")
        assert profile is not None
        assert profile.name == "rektslug-glass"

    def test_unknown_profile_raises(self):
        from src.liquidationheatmap.models.profiles import get_profile

        with pytest.raises(KeyError):
            get_profile("nonexistent-profile")

    def test_profile_has_leverage_weights(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-ank")
        assert isinstance(profile.leverage_weights, dict)
        assert len(profile.leverage_weights) > 0
        assert abs(sum(profile.leverage_weights.values()) - 1.0) < 0.01

    def test_profile_has_bin_size_fn(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-ank")
        assert callable(profile.get_bin_size)
        assert isinstance(profile.get_bin_size(timeframe_days=1), float)
        assert profile.get_bin_size(timeframe_days=1) > 0

    def test_ank_profile_supports_symbol_specific_overrides(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-ank")
        assert profile.get_bin_size(timeframe_days=1, symbol="BTCUSDT") == 10.0
        assert profile.get_bin_size(timeframe_days=7, symbol="BTCUSDT") == 12.0
        assert profile.get_bin_size(timeframe_days=7, symbol="ETHUSDT") == 1.65

    def test_ank_profile_supports_side_weight_overrides(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-ank")
        assert profile.get_side_weights("BTCUSDT", 1) == {"buy": 0.62, "sell": 1.0}
        assert profile.get_side_weights("BTCUSDT", 7) == {"buy": 0.42, "sell": 1.0}
        assert profile.get_side_weights("DOGEUSDT", 1) == {"buy": 1.0, "sell": 1.0}

    def test_ank_profile_supports_btc_leverage_weight_overrides(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-ank")
        assert profile.get_leverage_weights("BTCUSDT", 1) == {
            25: 0.28,
            50: 0.34,
            100: 0.38,
        }
        assert profile.get_leverage_weights("BTCUSDT", 7) == {
            25: 0.28,
            50: 0.34,
            100: 0.38,
        }
        assert profile.get_leverage_weights("ETHUSDT", 1) == profile.leverage_weights

    def test_glass_profile_supports_leverage_weight_overrides(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-glass")
        assert profile.get_leverage_weights("BTCUSDT", 1) == {
            5: 0.15,
            10: 0.30,
            25: 0.25,
            50: 0.20,
            100: 0.10,
        }
        assert profile.get_leverage_weights("ETHUSDT", 1) == profile.leverage_weights
        assert profile.get_leverage_weights("BTCUSDT", 7) == profile.leverage_weights

    def test_glass_profile_supports_symbol_specific_overrides(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-glass")
        assert profile.get_bin_size(timeframe_days=1, symbol="BTCUSDT") == 100.0
        assert profile.get_bin_size(timeframe_days=7, symbol="ETHUSDT") == 3.5
        assert profile.get_side_weights("BTCUSDT", 1) == {"buy": 0.9, "sell": 1.0}
        assert profile.get_side_weights("ETHUSDT", 1) == {"buy": 1.1, "sell": 1.0}
        assert profile.get_side_weights("BTCUSDT", 7) == {"buy": 0.4, "sell": 1.0}

    def test_default_profile_matches_current_behavior(self):
        """rektslug-default must reproduce the existing hardcoded parameters."""
        from src.liquidationheatmap.models.profiles import get_profile

        default = get_profile("rektslug-default")
        assert default.leverage_weights == {
            5: 0.15,
            10: 0.30,
            25: 0.25,
            50: 0.20,
            100: 0.10,
        }
        assert default.get_bin_size(timeframe_days=1) == 100.0
        assert default.get_bin_size(timeframe_days=7) == 100.0
        assert default.get_bin_size(timeframe_days=30) == 250.0
        assert default.get_bin_size(timeframe_days=365) == 500.0

    def test_ank_profile_excludes_low_leverage(self):
        """rektslug-ank should not include 5x/10x (CoinAnK starts at 25x)."""
        from src.liquidationheatmap.models.profiles import get_profile

        ank = get_profile("rektslug-ank")
        assert 5 not in ank.leverage_weights
        assert 10 not in ank.leverage_weights
        assert 25 in ank.leverage_weights

    def test_list_profiles(self):
        from src.liquidationheatmap.models.profiles import list_profiles

        names = list_profiles()
        assert "rektslug-default" in names
        assert "rektslug-ank" in names
        assert "rektslug-glass" in names


class TestProfileMetadata:
    """Reports and manifests must include profile identity."""

    def test_profile_to_dict(self):
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-ank")
        d = profile.to_dict()
        assert d["name"] == "rektslug-ank"
        assert "leverage_weights" in d
        assert "bin_size_1d" in d
        assert "bin_size_1w" in d
        assert "bin_size_overrides" in d
        assert "leverage_weight_overrides" in d
        assert "side_weight_overrides" in d

    def test_profile_round_trip(self):
        """Profile dict must contain enough info to reproduce the config."""
        from src.liquidationheatmap.models.profiles import get_profile

        profile = get_profile("rektslug-ank")
        d = profile.to_dict()
        assert d["name"] == profile.name
        assert d["leverage_weights"] == {
            str(k): v for k, v in profile.leverage_weights.items()
        }
