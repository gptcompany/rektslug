"""Nautilus Trader native Data subclass for liquidation map events.

This module requires nautilus_trader to be installed.
For standalone use without NT, use data.py instead.
"""

from __future__ import annotations

from src.liquidationheatmap.nautilus import _check_nautilus

_check_nautilus()

from nautilus_trader.core.data import Data  # noqa: E402

from src.liquidationheatmap.nautilus.data import LiquidationMapData  # noqa: E402


class NTLiquidationMapData(Data):
    """NT-native Data subclass wrapping LiquidationMapData.

    Passed directly to engine.add_data(). The backtest kernel replays
    these events in timestamp order alongside bars/ticks.

    Strategy receives via on_data():
        if isinstance(data, NTLiquidationMapData):
            liq = data.liq_data  # access LiquidationMapData fields
    """

    def __init__(self, liq_data: LiquidationMapData) -> None:
        self._liq_data = liq_data

    @property
    def ts_event(self) -> int:
        return self._liq_data.ts_event

    @property
    def ts_init(self) -> int:
        return self._liq_data.ts_init

    @property
    def liq_data(self) -> LiquidationMapData:
        return self._liq_data

    @property
    def expert_id(self) -> str:
        return self._liq_data.expert_id

    @property
    def symbol(self) -> str:
        return self._liq_data.symbol

    @property
    def exchange(self) -> str:
        return self._liq_data.exchange

    @property
    def reference_price(self) -> float:
        return self._liq_data.reference_price

    @property
    def net_imbalance(self) -> float:
        return self._liq_data.net_imbalance

    @property
    def nearest_long_liq(self) -> float:
        return self._liq_data.nearest_long_liq

    @property
    def nearest_short_liq(self) -> float:
        return self._liq_data.nearest_short_liq

    @property
    def long_distance_pct(self) -> float:
        return self._liq_data.long_distance_pct

    @property
    def short_distance_pct(self) -> float:
        return self._liq_data.short_distance_pct

    @property
    def total_long_volume(self) -> float:
        return self._liq_data.total_long_volume

    @property
    def total_short_volume(self) -> float:
        return self._liq_data.total_short_volume

    def __repr__(self) -> str:
        return (
            f"NTLiquidationMapData("
            f"expert={self.expert_id}, "
            f"symbol={self.symbol}, "
            f"imbalance={self.net_imbalance:.3f}, "
            f"ts_event={self.ts_event})"
        )
