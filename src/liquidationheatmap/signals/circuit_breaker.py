"""Circuit breaker for liquidation signal acceptance."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class TripReason(Enum):
    CONSECUTIVE_LOSSES = "consecutive_losses"
    SESSION_DRAWDOWN = "session_drawdown"
    RATE_LIMIT = "rate_limit"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    max_consecutive_losses: int = 5
    max_session_drawdown: float = -50.0
    max_signals_per_hour: int = 10
    cooldown_secs: int = 300


@dataclass
class CircuitBreakerState:
    symbol: str
    consecutive_losses: int = 0
    session_pnl: float = 0.0
    accepted_timestamps: list[float] = field(default_factory=list)
    tripped: bool = False
    trip_reason: Optional[TripReason] = None
    tripped_at: Optional[float] = None


class CircuitBreaker:
    def __init__(
        self,
        config: CircuitBreakerConfig,
        on_trip: Optional[Callable[[str, TripReason], None]] = None,
    ):
        self.config = config
        self.on_trip = on_trip
        self._states: dict[str, CircuitBreakerState] = {}

    def get_state(self, symbol: str) -> CircuitBreakerState:
        if symbol not in self._states:
            self._states[symbol] = CircuitBreakerState(symbol=symbol)
        return self._states[symbol]

    def check(self, symbol: str) -> tuple[bool, Optional[str]]:
        state = self.get_state(symbol)

        if state.tripped:
            if self._should_auto_reset(state):
                self._do_reset(state)
            else:
                reason_str = f"circuit_breaker:{state.trip_reason.value}"
                return False, reason_str

        # Check consecutive losses
        if state.consecutive_losses >= self.config.max_consecutive_losses:
            self._trip(state, TripReason.CONSECUTIVE_LOSSES)
            return False, f"circuit_breaker:{TripReason.CONSECUTIVE_LOSSES.value}"

        # Check session drawdown
        if state.session_pnl <= self.config.max_session_drawdown:
            self._trip(state, TripReason.SESSION_DRAWDOWN)
            return False, f"circuit_breaker:{TripReason.SESSION_DRAWDOWN.value}"

        # Check rate limit (sliding 1h window)
        now = time.time()
        cutoff = now - 3600
        state.accepted_timestamps = [
            t for t in state.accepted_timestamps if t > cutoff
        ]
        if len(state.accepted_timestamps) >= self.config.max_signals_per_hour:
            self._trip(state, TripReason.RATE_LIMIT)
            return False, f"circuit_breaker:{TripReason.RATE_LIMIT.value}"

        return True, None

    def record_outcome(self, symbol: str, pnl: float) -> None:
        state = self.get_state(symbol)
        state.session_pnl += pnl
        if pnl < 0:
            state.consecutive_losses += 1
        else:
            state.consecutive_losses = 0

        # Check if we should trip after recording
        if (
            not state.tripped
            and state.consecutive_losses >= self.config.max_consecutive_losses
        ):
            self._trip(state, TripReason.CONSECUTIVE_LOSSES)
        elif (
            not state.tripped
            and state.session_pnl <= self.config.max_session_drawdown
        ):
            self._trip(state, TripReason.SESSION_DRAWDOWN)

    def record_acceptance(self, symbol: str) -> None:
        state = self.get_state(symbol)
        state.accepted_timestamps.append(time.time())

    def reset(self, symbol: str) -> None:
        state = self.get_state(symbol)
        self._do_reset(state)

    def _trip(self, state: CircuitBreakerState, reason: TripReason) -> None:
        state.tripped = True
        state.trip_reason = reason
        state.tripped_at = time.time()
        if self.on_trip:
            self.on_trip(state.symbol, reason)

    def _do_reset(self, state: CircuitBreakerState) -> None:
        state.tripped = False
        state.trip_reason = None
        state.tripped_at = None
        state.consecutive_losses = 0

    def _should_auto_reset(self, state: CircuitBreakerState) -> bool:
        if self.config.cooldown_secs == 0:
            return False
        if state.tripped_at is None:
            return False
        return (time.time() - state.tripped_at) >= self.config.cooldown_secs
