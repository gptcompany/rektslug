"""Shadow tracker for hypothetical PnL and circuit breaker calibration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CalibrationSummary:
    total_signals: int = 0
    profitable: int = 0
    signal_quality_score: float = 0.0
    longest_losing_streak: int = 0
    max_drawdown: float = 0.0
    total_pnl: float = 0.0
    suggested_max_consecutive_losses: int = 1
    suggested_max_drawdown: float = 0.0


@dataclass
class _OpenPosition:
    signal_id: str
    symbol: str
    entry_price: float
    side: str  # "long" or "short"


@dataclass
class _ClosedPosition:
    signal_id: str
    symbol: str
    entry_price: float
    exit_price: float
    side: str
    pnl: float


class ShadowTracker:
    def __init__(self) -> None:
        self._open: dict[str, _OpenPosition] = {}
        self._closed: list[_ClosedPosition] = []

    def record_entry(
        self, signal_id: str, symbol: str, price: float, side: str
    ) -> None:
        self._open[signal_id] = _OpenPosition(
            signal_id=signal_id, symbol=symbol, entry_price=price, side=side
        )

    def record_exit(self, signal_id: str, exit_price: float) -> None:
        pos = self._open.pop(signal_id, None)
        if pos is None:
            return
        if pos.side == "long":
            pnl = exit_price - pos.entry_price
        else:
            pnl = pos.entry_price - exit_price
        self._closed.append(
            _ClosedPosition(
                signal_id=pos.signal_id,
                symbol=pos.symbol,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                side=pos.side,
                pnl=pnl,
            )
        )

    def get_closed_positions(self) -> list[dict]:
        return [
            {
                "signal_id": p.signal_id,
                "symbol": p.symbol,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "side": p.side,
                "pnl": p.pnl,
            }
            for p in self._closed
        ]

    def get_calibration(self) -> CalibrationSummary:
        if not self._closed:
            return CalibrationSummary()

        pnls = [p.pnl for p in self._closed]
        profitable = sum(1 for p in pnls if p > 0)
        total = len(pnls)

        # Longest losing streak
        longest_streak = 0
        current_streak = 0
        for p in pnls:
            if p < 0:
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            else:
                current_streak = 0

        # Max drawdown (cumulative)
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            cumulative += p
            if cumulative > peak:
                peak = cumulative
            dd = cumulative - peak
            if dd < max_dd:
                max_dd = dd

        return CalibrationSummary(
            total_signals=total,
            profitable=profitable,
            signal_quality_score=profitable / total if total > 0 else 0.0,
            longest_losing_streak=longest_streak,
            max_drawdown=max_dd,
            total_pnl=sum(pnls),
            suggested_max_consecutive_losses=longest_streak + 1,
            suggested_max_drawdown=max_dd * 1.5,
        )
