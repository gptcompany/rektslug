"""Circuit breaker tests — TDD RED phase."""

import time

import pytest

from src.liquidationheatmap.signals.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    TripReason,
)


@pytest.fixture
def cb():
    return CircuitBreaker(CircuitBreakerConfig())


@pytest.fixture
def cb_no_cooldown():
    return CircuitBreaker(CircuitBreakerConfig(cooldown_secs=0))


def test_allows_signal_when_no_losses(cb):
    allowed, reason = cb.check("BTCUSDT")
    assert allowed is True
    assert reason is None


def test_trips_after_max_consecutive_losses(cb):
    for _ in range(5):
        cb.record_outcome("BTCUSDT", -1.0)
    allowed, reason = cb.check("BTCUSDT")
    assert allowed is False
    assert reason == "circuit_breaker:consecutive_losses"


def test_resets_consecutive_on_win(cb):
    for _ in range(4):
        cb.record_outcome("BTCUSDT", -1.0)
    cb.record_outcome("BTCUSDT", 2.0)
    allowed, reason = cb.check("BTCUSDT")
    assert allowed is True
    assert reason is None
    state = cb.get_state("BTCUSDT")
    assert state.consecutive_losses == 0


def test_trips_on_session_drawdown(cb):
    cb.record_outcome("BTCUSDT", -51.0)
    allowed, reason = cb.check("BTCUSDT")
    assert allowed is False
    assert reason == "circuit_breaker:session_drawdown"


def test_trips_on_rate_limit(cb):
    for _ in range(10):
        cb.record_acceptance("BTCUSDT")
    allowed, reason = cb.check("BTCUSDT")
    assert allowed is False
    assert reason == "circuit_breaker:rate_limit"


def test_rate_limit_window_slides(cb):
    old = time.time() - 3700  # over 1 hour ago
    state = cb.get_state("BTCUSDT")
    state.accepted_timestamps = [old] * 10
    allowed, reason = cb.check("BTCUSDT")
    assert allowed is True
    assert reason is None


def test_manual_reset_clears_trip(cb):
    for _ in range(5):
        cb.record_outcome("BTCUSDT", -1.0)
    allowed, _ = cb.check("BTCUSDT")
    assert allowed is False
    cb.reset("BTCUSDT")
    allowed, reason = cb.check("BTCUSDT")
    assert allowed is True
    assert reason is None


def test_auto_reset_after_cooldown(cb):
    for _ in range(5):
        cb.record_outcome("BTCUSDT", -1.0)
    allowed, _ = cb.check("BTCUSDT")
    assert allowed is False
    state = cb.get_state("BTCUSDT")
    state.tripped_at = time.time() - 301  # past cooldown
    allowed, reason = cb.check("BTCUSDT")
    assert allowed is True


def test_cooldown_zero_means_manual_only(cb_no_cooldown):
    for _ in range(5):
        cb_no_cooldown.record_outcome("BTCUSDT", -1.0)
    allowed, _ = cb_no_cooldown.check("BTCUSDT")
    assert allowed is False
    state = cb_no_cooldown.get_state("BTCUSDT")
    state.tripped_at = time.time() - 99999
    allowed, _ = cb_no_cooldown.check("BTCUSDT")
    assert allowed is False  # no auto-reset


def test_on_trip_callback_called(cb):
    trips = []
    cb.on_trip = lambda symbol, reason: trips.append((symbol, reason))
    for _ in range(5):
        cb.record_outcome("BTCUSDT", -1.0)
    assert len(trips) == 1
    assert trips[0] == ("BTCUSDT", TripReason.CONSECUTIVE_LOSSES)
