"""Calibration profiles for the rektslug liq-map model.

Each profile defines a named set of parameters (leverage weights, bin sizing)
that can be selected at runtime without changing the default behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class CalibrationProfile:
    """A named set of model parameters for liq-map calculation."""

    name: str
    leverage_weights: dict[int, float]
    _bin_size_fn: Callable[..., float] = field(repr=False)
    bin_size_overrides: dict[tuple[str, int], float] = field(default_factory=dict)
    leverage_weight_overrides: dict[tuple[str, int], dict[int, float]] = field(default_factory=dict)
    side_weight_overrides: dict[tuple[str, int], dict[str, float]] = field(default_factory=dict)

    def get_bin_size(
        self,
        timeframe_days: int,
        current_price: float | None = None,
        symbol: str | None = None,
    ) -> float:
        """Return bin size, optionally adapting to current price for finer control."""
        if symbol:
            override = self.bin_size_overrides.get((symbol.upper(), timeframe_days))
            if override is not None:
                return override

        import inspect

        sig = inspect.signature(self._bin_size_fn)
        if len(sig.parameters) >= 3:
            return self._bin_size_fn(timeframe_days, current_price, symbol)
        if len(sig.parameters) >= 2 and current_price is not None:
            return self._bin_size_fn(timeframe_days, current_price)
        return self._bin_size_fn(timeframe_days)

    def get_side_weights(self, symbol: str, timeframe_days: int) -> dict[str, float]:
        """Return side weights used to rebalance long/short bias for a matrix entry."""
        return self.side_weight_overrides.get(
            (symbol.upper(), timeframe_days),
            {"buy": 1.0, "sell": 1.0},
        )

    def get_leverage_weights(self, symbol: str, timeframe_days: int) -> dict[int, float]:
        """Return leverage weights for a matrix entry, falling back to the profile default."""
        return self.leverage_weight_overrides.get(
            (symbol.upper(), timeframe_days),
            self.leverage_weights,
        )

    def to_dict(self) -> dict:
        bin_overrides = {
            f"{symbol}:{days}d": value
            for (symbol, days), value in sorted(self.bin_size_overrides.items())
        }
        leverage_overrides = {
            f"{symbol}:{days}d": {str(k): v for k, v in weights.items()}
            for (symbol, days), weights in sorted(self.leverage_weight_overrides.items())
        }
        side_overrides = {
            f"{symbol}:{days}d": weights
            for (symbol, days), weights in sorted(self.side_weight_overrides.items())
        }
        return {
            "name": self.name,
            "leverage_weights": {str(k): v for k, v in self.leverage_weights.items()},
            "bin_size_1d": self.get_bin_size(1),
            "bin_size_1w": self.get_bin_size(7),
            "bin_size_30d": self.get_bin_size(30),
            "bin_size_overrides": bin_overrides,
            "leverage_weight_overrides": leverage_overrides,
            "side_weight_overrides": side_overrides,
        }


def _default_bin_size(timeframe_days: int) -> float:
    """Current hardcoded bin-size logic from the /levels endpoint."""
    if timeframe_days <= 7:
        return 100.0
    elif timeframe_days <= 30:
        return 250.0
    return 500.0


def _ank_bin_size(
    timeframe_days: int,
    current_price: float | None = None,
    symbol: str | None = None,
) -> float:
    """CoinAnK-aligned bin sizing: adaptive to price for ~400-800 bucket target.

    CoinAnK uses price_step 0.5-1.0 regardless of symbol, producing 400-800 buckets.
    We target bin_size ≈ current_price * 0.0003 for short timeframes, which gives:
    - BTC (~87k): bin_size ≈ 26 → ~600 buckets over ±10% range
    - ETH (~2k): bin_size ≈ 0.6 → ~600 buckets over ±10% range
    """
    if current_price is not None and current_price > 0:
        if timeframe_days <= 1:
            return round(max(0.5, current_price * 0.0003), 2)
        elif timeframe_days <= 7:
            return round(max(1.0, current_price * 0.0005), 2)
        elif timeframe_days <= 30:
            return round(max(2.0, current_price * 0.001), 2)
        return round(max(5.0, current_price * 0.002), 2)
    # Fallback without price context
    if timeframe_days <= 7:
        return 10.0
    elif timeframe_days <= 30:
        return 25.0
    return 50.0


_DEFAULT_LEVERAGE_WEIGHTS = {
    5: 0.15,
    10: 0.30,
    25: 0.25,
    50: 0.20,
    100: 0.10,
}

_ANK_LEVERAGE_WEIGHTS = {
    25: 0.35,
    50: 0.35,
    100: 0.30,
}

_ANK_BTC_LEVERAGE_WEIGHTS = {
    25: 0.28,
    50: 0.34,
    100: 0.38,
}

_GLASS_LEVERAGE_WEIGHTS = {
    25: 0.30,
    50: 0.35,
    100: 0.35,
}


_PROFILES: dict[str, CalibrationProfile] = {
    "rektslug-default": CalibrationProfile(
        name="rektslug-default",
        leverage_weights=_DEFAULT_LEVERAGE_WEIGHTS,
        _bin_size_fn=_default_bin_size,
    ),
    "rektslug-ank": CalibrationProfile(
        name="rektslug-ank",
        leverage_weights=_ANK_LEVERAGE_WEIGHTS,
        _bin_size_fn=_ank_bin_size,
        bin_size_overrides={
            ("BTCUSDT", 1): 10.0,
            ("BTCUSDT", 7): 12.0,
            ("ETHUSDT", 1): 0.45,
            ("ETHUSDT", 7): 1.65,
        },
        leverage_weight_overrides={
            ("BTCUSDT", 1): _ANK_BTC_LEVERAGE_WEIGHTS,
            ("BTCUSDT", 7): _ANK_BTC_LEVERAGE_WEIGHTS,
        },
        side_weight_overrides={
            ("BTCUSDT", 1): {"buy": 0.62, "sell": 1.0},
            ("BTCUSDT", 7): {"buy": 0.42, "sell": 1.0},
            ("ETHUSDT", 1): {"buy": 0.66, "sell": 1.0},
            ("ETHUSDT", 7): {"buy": 0.30, "sell": 1.0},
        },
    ),
    "rektslug-glass": CalibrationProfile(
        name="rektslug-glass",
        leverage_weights=_GLASS_LEVERAGE_WEIGHTS,
        _bin_size_fn=_ank_bin_size,
        bin_size_overrides={
            ("BTCUSDT", 1): 100.0,
            ("BTCUSDT", 7): 120.0,
            ("ETHUSDT", 1): 1.8,
            ("ETHUSDT", 7): 3.5,
        },
        leverage_weight_overrides={
            ("BTCUSDT", 1): _DEFAULT_LEVERAGE_WEIGHTS,
        },
        side_weight_overrides={
            ("BTCUSDT", 1): {"buy": 0.9, "sell": 1.0},
            ("BTCUSDT", 7): {"buy": 0.4, "sell": 1.0},
            ("ETHUSDT", 1): {"buy": 1.1, "sell": 1.0},
            ("ETHUSDT", 7): {"buy": 0.45, "sell": 1.0},
        },
    ),
}


def get_profile(name: str) -> CalibrationProfile:
    """Return a named calibration profile.

    Raises:
        KeyError: If the profile name is not registered.
    """
    if name not in _PROFILES:
        raise KeyError(f"Unknown calibration profile: {name!r}")
    return _PROFILES[name]


def list_profiles() -> list[str]:
    """Return the names of all registered profiles."""
    return list(_PROFILES.keys())
