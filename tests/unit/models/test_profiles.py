"""Unit tests for calibration profiles."""

import pytest
from src.liquidationheatmap.models.profiles import (
    CalibrationProfile,
    get_profile,
    list_profiles,
    _default_bin_size,
    _ank_bin_size,
)

class TestCalibrationProfiles:
    def test_list_profiles(self):
        profiles = list_profiles()
        assert "rektslug-default" in profiles
        assert "rektslug-ank" in profiles
        assert "rektslug-ank-public" in profiles
        assert "rektslug-glass" in profiles

    def test_get_profile_success(self):
        profile = get_profile("rektslug-default")
        assert profile.name == "rektslug-default"

    def test_get_profile_failure(self):
        with pytest.raises(KeyError):
            get_profile("nonexistent")

    def test_default_bin_size(self):
        assert _default_bin_size(1) == 100.0
        assert _default_bin_size(7) == 100.0
        assert _default_bin_size(14) == 250.0
        assert _default_bin_size(30) == 250.0
        assert _default_bin_size(90) == 500.0

    def test_ank_bin_size(self):
        # With price BTC ~90k
        assert _ank_bin_size(1, 90000.0) == round(90000.0 * 0.0003, 2)
        assert _ank_bin_size(7, 90000.0) == round(90000.0 * 0.0005, 2)
        assert _ank_bin_size(30, 90000.0) == round(90000.0 * 0.001, 2)
        assert _ank_bin_size(90, 90000.0) == round(90000.0 * 0.002, 2)
        
        # Fallback without price
        assert _ank_bin_size(1) == 10.0
        assert _ank_bin_size(30) == 25.0
        assert _ank_bin_size(90) == 50.0

    def test_profile_get_bin_size_override(self):
        profile = get_profile("rektslug-ank")
        # BTCUSDT 1d has override 15.0
        assert profile.get_bin_size(1, symbol="BTCUSDT") == 15.0
        # ETHUSDT 7d has override 1.65
        assert profile.get_bin_size(7, symbol="ETHUSDT") == 1.65
        # No override for LTCUSDT, uses _ank_bin_size logic
        assert profile.get_bin_size(1, current_price=100.0, symbol="LTCUSDT") == 0.5 # max(0.5, 100*0.0003)

    def test_profile_get_side_weights(self):
        profile = get_profile("rektslug-ank")
        assert profile.get_side_weights("BTCUSDT", 1) == {"buy": 0.95, "sell": 1.0}
        assert profile.get_side_weights("UNKNOWN", 1) == {"buy": 1.0, "sell": 1.0}

    def test_public_ank_profile_exposes_visual_btc_overrides(self):
        profile = get_profile("rektslug-ank-public")
        assert profile.get_bin_size(1, symbol="BTCUSDT") == 10.0
        assert profile.get_bin_size(7, symbol="BTCUSDT") == 12.0
        assert profile.get_side_weights("BTCUSDT", 1) == {"buy": 0.25, "sell": 2.5}
        assert profile.get_side_weights("BTCUSDT", 7) == {"buy": 0.42, "sell": 1.0}
        assert profile.get_leverage_weights("BTCUSDT", 1) == {
            25: 0.28,
            50: 0.34,
            100: 0.38,
        }

    def test_profile_get_leverage_weights(self):
        profile = get_profile("rektslug-glass")
        # BTCUSDT 1d has override to default leverage weights
        weights = profile.get_leverage_weights("BTCUSDT", 1)
        assert weights[5] == 0.15
        
        # UNKNOWN uses profile default
        weights_default = profile.get_leverage_weights("UNKNOWN", 1)
        assert weights_default[100] == 0.35

    def test_profile_to_dict(self):
        profile = get_profile("rektslug-default")
        d = profile.to_dict()
        assert d["name"] == "rektslug-default"
        assert "leverage_weights" in d
        assert "bin_size_1d" in d
        assert "bin_size_overrides" in d
