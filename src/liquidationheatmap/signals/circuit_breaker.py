"""Circuit breaker for liquidation signal acceptance."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

import duckdb


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


class CircuitBreakerStore:
    """DuckDB persistence for circuit breaker state."""

    def __init__(
        self,
        db_path: str = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        read_only: bool = False,
    ):
        self.db_path = db_path
        self._read_only = read_only
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self.db_path, read_only=self._read_only)
            if not self._read_only:
                self._ensure_table()
        return self._conn

    def _ensure_table(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS circuit_breaker_state (
                symbol VARCHAR PRIMARY KEY,
                consecutive_losses INT NOT NULL DEFAULT 0,
                session_pnl DOUBLE NOT NULL DEFAULT 0.0,
                tripped BOOLEAN NOT NULL DEFAULT FALSE,
                trip_reason VARCHAR,
                tripped_at DOUBLE,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def save_state(self, state: CircuitBreakerState) -> None:
        try:
            now = datetime.now(timezone.utc)
            trip_reason_val = state.trip_reason.value if state.trip_reason else None
            self.conn.execute("""
                INSERT INTO circuit_breaker_state
                    (symbol, consecutive_losses, session_pnl, tripped, trip_reason, tripped_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (symbol) DO UPDATE SET
                    consecutive_losses = EXCLUDED.consecutive_losses,
                    session_pnl = EXCLUDED.session_pnl,
                    tripped = EXCLUDED.tripped,
                    trip_reason = EXCLUDED.trip_reason,
                    tripped_at = EXCLUDED.tripped_at,
                    updated_at = EXCLUDED.updated_at
            """, [state.symbol, state.consecutive_losses, state.session_pnl,
                  state.tripped, trip_reason_val, state.tripped_at, now])
        except Exception as e:
            logging.error(f"Failed to save circuit breaker state for {state.symbol}: {e}")

    def load_state(self, symbol: str) -> Optional[CircuitBreakerState]:
        try:
            row = self.conn.execute(
                "SELECT consecutive_losses, session_pnl, tripped, trip_reason, tripped_at "
                "FROM circuit_breaker_state WHERE symbol = ?",
                [symbol],
            ).fetchone()
            if row is None:
                return None
            trip_reason = TripReason(row[3]) if row[3] else None
            return CircuitBreakerState(
                symbol=symbol,
                consecutive_losses=row[0],
                session_pnl=row[1],
                tripped=row[2],
                trip_reason=trip_reason,
                tripped_at=row[4],
            )
        except Exception as e:
            logging.error(f"Failed to load circuit breaker state for {symbol}: {e}")
            return None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
