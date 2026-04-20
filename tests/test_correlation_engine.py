"""Tests for prediction-vs-reality correlation engine."""

from src.liquidationheatmap.signals.correlation import CorrelationEngine


class TestCorrelationEngine:
    def test_match_within_price_threshold(self):
        """Signal at $72000, event at $72100 (0.14%) → match."""
        engine = CorrelationEngine(price_threshold_pct=1.0, time_window_secs=1800)
        engine.register_signal("sig1", "BTCUSDT", 72000.0, "long")

        matches = engine.process_event("BTCUSDT", 72100.0, "long", 0.5)
        assert len(matches) == 1
        assert matches[0].signal_id == "sig1"

    def test_no_match_outside_price_threshold(self):
        engine = CorrelationEngine(price_threshold_pct=0.1, time_window_secs=1800)
        engine.register_signal("sig1", "BTCUSDT", 72000.0, "long")

        matches = engine.process_event("BTCUSDT", 72100.0, "long", 0.5)
        assert len(matches) == 0

    def test_no_match_wrong_side(self):
        engine = CorrelationEngine(price_threshold_pct=1.0, time_window_secs=1800)
        engine.register_signal("sig1", "BTCUSDT", 72000.0, "long")

        matches = engine.process_event("BTCUSDT", 72000.0, "short", 0.5)
        assert len(matches) == 0

    def test_multiple_signals_match(self):
        engine = CorrelationEngine(price_threshold_pct=1.0, time_window_secs=1800)
        engine.register_signal("sig1", "BTCUSDT", 72000.0, "long")
        engine.register_signal("sig2", "BTCUSDT", 72200.0, "long")

        matches = engine.process_event("BTCUSDT", 72100.0, "long", 0.5)
        assert len(matches) == 2
        assert {m.signal_id for m in matches} == {"sig1", "sig2"}

    def test_match_canonical_symbol(self):
        """Signal has BTCUSDT, WS event has BTCUSDT-PERP → match."""
        engine = CorrelationEngine(price_threshold_pct=1.0, time_window_secs=1800)
        engine.register_signal("sig1", "BTCUSDT", 72000.0, "long")

        matches = engine.process_event("BTCUSDT-PERP", 72100.0, "long", 0.5)
        assert len(matches) == 1
        assert matches[0].signal_id == "sig1"

    def test_single_match_per_signal(self):
        """A signal should only match once."""
        engine = CorrelationEngine(price_threshold_pct=1.0, time_window_secs=1800)
        engine.register_signal("sig1", "BTCUSDT", 72000.0, "long")

        # First event matches
        matches1 = engine.process_event("BTCUSDT", 72100.0, "long", 0.5)
        assert len(matches1) == 1

        # Second event does not match since signal is consumed
        matches2 = engine.process_event("BTCUSDT", 72100.0, "long", 0.5)
        assert len(matches2) == 0
