"""Shadow tracker tests — TDD RED then GREEN."""

import pytest

from src.liquidationheatmap.signals.shadow import CalibrationSummary, ShadowTracker


@pytest.fixture
def tracker():
    return ShadowTracker()


def test_hypothetical_pnl_long(tracker):
    tracker.record_entry("sig-1", "BTCUSDT", 100.0, "long")
    tracker.record_exit("sig-1", 105.0)
    positions = tracker.get_closed_positions()
    assert len(positions) == 1
    assert positions[0]["pnl"] == pytest.approx(5.0)


def test_hypothetical_pnl_short(tracker):
    tracker.record_entry("sig-1", "BTCUSDT", 100.0, "short")
    tracker.record_exit("sig-1", 95.0)
    positions = tracker.get_closed_positions()
    assert len(positions) == 1
    assert positions[0]["pnl"] == pytest.approx(5.0)


def test_hypothetical_pnl_short_loss(tracker):
    tracker.record_entry("sig-1", "BTCUSDT", 100.0, "short")
    tracker.record_exit("sig-1", 110.0)
    positions = tracker.get_closed_positions()
    assert positions[0]["pnl"] == pytest.approx(-10.0)


def test_calibration_with_known_data(tracker):
    # 3 wins, 2 consecutive losses at the end
    entries = [
        ("s1", 100.0, "long", 105.0),  # +5
        ("s2", 100.0, "long", 103.0),  # +3
        ("s3", 100.0, "short", 95.0),  # +5
        ("s4", 100.0, "long", 98.0),   # -2
        ("s5", 100.0, "long", 97.0),   # -3
    ]
    for sig_id, entry, side, exit_p in entries:
        tracker.record_entry(sig_id, "BTCUSDT", entry, side)
        tracker.record_exit(sig_id, exit_p)

    cal = tracker.get_calibration()
    assert isinstance(cal, CalibrationSummary)
    assert cal.total_signals == 5
    assert cal.profitable == 3
    assert cal.signal_quality_score == pytest.approx(0.6)
    assert cal.longest_losing_streak == 2
    assert cal.suggested_max_consecutive_losses == 3  # streak + 1
    assert cal.max_drawdown == pytest.approx(-5.0)  # -2 + -3
    assert cal.suggested_max_drawdown == pytest.approx(-7.5)  # max_dd * 1.5


def test_losing_streak_detection(tracker):
    # L L W L L L W
    pnls = [-1, -1, 1, -1, -1, -1, 1]
    for i, pnl in enumerate(pnls):
        entry = 100.0
        side = "long"
        exit_p = entry + pnl
        tracker.record_entry(f"s{i}", "BTCUSDT", entry, side)
        tracker.record_exit(f"s{i}", exit_p)
    cal = tracker.get_calibration()
    assert cal.longest_losing_streak == 3


def test_empty_calibration(tracker):
    cal = tracker.get_calibration()
    assert cal.total_signals == 0
    assert cal.signal_quality_score == 0.0
    assert cal.longest_losing_streak == 0
    assert cal.suggested_max_consecutive_losses == 1
