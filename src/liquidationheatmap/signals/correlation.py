import time
from dataclasses import dataclass


@dataclass
class RegisteredSignal:
    signal_id: str
    symbol: str
    price: float
    side: str
    timestamp: float


@dataclass
class CorrelationMatch:
    signal_id: str
    event_price: float
    event_side: str
    event_size: float
    matched_at: float


class CorrelationEngine:
    def __init__(self, price_threshold_pct: float = 1.0, time_window_secs: int = 1800):
        self.price_threshold_pct = price_threshold_pct
        self.time_window_secs = time_window_secs
        self._signals: list[RegisteredSignal] = []
        self.matches: list[CorrelationMatch] = []

    def register_signal(self, signal_id: str, symbol: str, price: float, side: str) -> None:
        self._signals.append(
            RegisteredSignal(
                signal_id=signal_id, symbol=symbol, price=price, side=side, timestamp=time.time()
            )
        )

    def process_event(
        self, symbol: str, event_price: float, side: str, size: float
    ) -> list[CorrelationMatch]:
        now = time.time()
        # Clean up old signals
        self._signals = [s for s in self._signals if now - s.timestamp <= self.time_window_secs]

        matches = []
        for s in self._signals:
            if s.symbol == symbol and s.side == side:
                diff_pct = abs(s.price - event_price) / s.price * 100
                if diff_pct <= self.price_threshold_pct:
                    match = CorrelationMatch(
                        signal_id=s.signal_id,
                        event_price=event_price,
                        event_side=side,
                        event_size=size,
                        matched_at=now,
                    )
                    matches.append(match)
                    self.matches.append(match)

        return matches
