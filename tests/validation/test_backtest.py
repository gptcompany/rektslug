"""Tests for backtest framework (T2.2-T2.4).

TDD RED phase: These tests define the backtest API.
"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.liquidationheatmap.validation import backtest
from src.liquidationheatmap.validation.backtest import (
    BacktestConfig,
    BacktestResult,
    PredictionMetrics,
    calculate_metrics,
    generate_backtest_report,
    get_actual_liquidations,
    get_predicted_zones,
    match_predictions_to_actuals,
    run_backtest,
)


class TestPredictionMetrics:
    """Test Precision/Recall/F1 calculation."""

    def test_perfect_predictions(self):
        """All predictions hit, all liquidations predicted."""
        metrics = calculate_metrics(
            true_positives=10,
            false_positives=0,
            false_negatives=0,
        )

        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1_score == 1.0

    def test_no_predictions(self):
        """No predictions made."""
        metrics = calculate_metrics(
            true_positives=0,
            false_positives=0,
            false_negatives=5,
        )

        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0

    def test_all_false_positives(self):
        """All predictions missed."""
        metrics = calculate_metrics(
            true_positives=0,
            false_positives=10,
            false_negatives=5,
        )

        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0

    def test_no_actual_liquidations_sets_recall_to_zero(self):
        """Recall should stay zero when there are predictions but no actual events."""
        metrics = calculate_metrics(
            true_positives=0,
            false_positives=3,
            false_negatives=0,
        )

        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0

    def test_balanced_metrics(self):
        """Typical case with mixed results."""
        # 6 TP, 4 FP, 2 FN
        # Precision = 6/(6+4) = 0.6
        # Recall = 6/(6+2) = 0.75
        # F1 = 2 * 0.6 * 0.75 / (0.6 + 0.75) = 0.667
        metrics = calculate_metrics(
            true_positives=6,
            false_positives=4,
            false_negatives=2,
        )

        assert metrics.precision == pytest.approx(0.6, rel=0.01)
        assert metrics.recall == pytest.approx(0.75, rel=0.01)
        assert metrics.f1_score == pytest.approx(0.667, rel=0.01)


class TestBacktestConfig:
    """Test backtest configuration."""

    def test_default_config(self):
        """Config has sensible defaults."""
        config = BacktestConfig(
            symbol="BTCUSDT",
            start_date=datetime(2024, 6, 1),
            end_date=datetime(2024, 12, 31),
        )

        assert config.symbol == "BTCUSDT"
        assert config.tolerance_pct == 1.0  # 1% default
        assert config.prediction_horizon_minutes == 60  # 1 hour default

    def test_custom_tolerance(self):
        """Custom tolerance levels."""
        config = BacktestConfig(
            symbol="BTCUSDT",
            start_date=datetime(2024, 6, 1),
            end_date=datetime(2024, 12, 31),
            tolerance_pct=0.5,
        )

        assert config.tolerance_pct == 0.5

    def test_config_to_dict_serializes_dates(self):
        """Config should serialize date fields for reports."""
        config = BacktestConfig(
            symbol="ETHUSDT",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )

        assert config.to_dict() == {
            "symbol": "ETHUSDT",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-01-31T00:00:00",
            "tolerance_pct": 1.0,
            "prediction_horizon_minutes": 60,
        }


class TestBacktestResult:
    """Test backtest result structure."""

    def test_result_has_metrics(self):
        """Result contains key metrics."""
        result = BacktestResult(
            config=BacktestConfig(
                symbol="BTCUSDT",
                start_date=datetime(2024, 6, 1),
                end_date=datetime(2024, 12, 31),
            ),
            metrics=PredictionMetrics(
                precision=0.7,
                recall=0.8,
                f1_score=0.75,
            ),
            true_positives=70,
            false_positives=30,
            false_negatives=18,
            total_predictions=100,
            total_liquidations=88,
        )

        assert result.metrics.f1_score == 0.75
        assert result.total_predictions == 100
        assert result.passed_gate(threshold=0.6)
        assert not result.passed_gate(threshold=0.8)

    def test_result_to_dict(self):
        """Result can be serialized."""
        result = BacktestResult(
            config=BacktestConfig(
                symbol="BTCUSDT",
                start_date=datetime(2024, 6, 1),
                end_date=datetime(2024, 12, 31),
            ),
            metrics=PredictionMetrics(
                precision=0.7,
                recall=0.8,
                f1_score=0.75,
            ),
            true_positives=70,
            false_positives=30,
            false_negatives=18,
            total_predictions=100,
            total_liquidations=88,
        )

        data = result.to_dict()

        assert "metrics" in data
        assert data["metrics"]["f1_score"] == 0.75
        assert data["symbol"] == "BTCUSDT"

    def test_result_to_dict_serializes_gate_and_error(self):
        """Serialized result should expose gate status and explicit error strings."""
        result = BacktestResult(
            config=BacktestConfig(
                symbol="BTCUSDT",
                start_date=datetime(2024, 6, 1),
                end_date=datetime(2024, 12, 31),
            ),
            metrics=PredictionMetrics(precision=0.2, recall=0.3, f1_score=0.24),
            error="db missing",
        )

        payload = result.to_dict()

        assert payload["gate_2_passed"] is False
        assert payload["error"] == "db missing"


class _FetchResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows


class _SequenceConn:
    def __init__(self, responses):
        self.responses = list(responses)
        self.executed = []
        self.closed = False

    def execute(self, query, params):
        self.executed.append((query, params))
        if not self.responses:
            raise AssertionError("Unexpected execute call")
        return _FetchResult(self.responses.pop(0))

    def close(self):
        self.closed = True


class TestQueryHelpers:
    """Test DB-backed helper functions with fake connections."""

    def test_get_predicted_zones_prefers_snapshots(self):
        conn = _SequenceConn(
            [[(70000.0, "long", 150000.0, 1.0)]]
        )

        rows = get_predicted_zones(conn, "BTCUSDT", datetime(2024, 1, 1))

        assert rows == [
            {
                "price": 70000.0,
                "side": "long",
                "volume": 150000.0,
                "confidence": 1.0,
            }
        ]
        assert "liquidation_snapshots" in conn.executed[0][0]

    def test_get_predicted_zones_falls_back_to_liquidation_levels(self):
        conn = _SequenceConn(
            [
                [],
                [(71000.0, "short", 200000.0, 0.8)],
            ]
        )

        rows = get_predicted_zones(conn, "BTCUSDT", datetime(2024, 1, 1))

        assert rows == [
            {
                "price": 71000.0,
                "side": "short",
                "volume": 200000.0,
                "confidence": 0.8,
            }
        ]
        assert "liquidation_levels" in conn.executed[1][0]

    def test_get_actual_liquidations_returns_empty_when_no_price_window(self):
        conn = _SequenceConn([None])

        rows = get_actual_liquidations(
            conn,
            "BTCUSDT",
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
        )

        assert rows == []

    def test_get_actual_liquidations_returns_long_and_short_extremes(self):
        conn = _SequenceConn([(65000.0, 72000.0)])

        rows = get_actual_liquidations(
            conn,
            "BTCUSDT",
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
        )

        assert rows == [
            {"price": 65000.0, "side": "long", "volume": 1.0},
            {"price": 72000.0, "side": "short", "volume": 1.0},
        ]


class TestMatching:
    """Test matching logic between predicted and actual zones."""

    def test_match_predictions_to_actuals_handles_empty_inputs(self):
        result = match_predictions_to_actuals([], [{"price": 1.0, "side": "long"}])
        assert result == (0, 0, 1, [], [{"price": 1.0, "side": "long"}], [])

    def test_match_predictions_to_actuals_requires_both_price_extremes(self):
        result = match_predictions_to_actuals(
            [{"price": 100.0, "side": "long"}],
            [{"price": 95.0, "side": "long"}],
        )

        assert result == (0, 0, 0, [], [], [])

    def test_match_predictions_to_actuals_tracks_matches_and_misses(self):
        predictions = [
            {"price": 95.5, "side": "long"},
            {"price": 105.8, "side": "short"},
        ]
        actuals = [
            {"price": 95.0, "side": "long"},
            {"price": 110.0, "side": "short"},
        ]

        tp, fp, fn, matched, missed, false_alarms = match_predictions_to_actuals(
            predictions,
            actuals,
            tolerance_pct=1.0,
        )

        assert tp == 1
        assert fp == 0
        assert fn == 1
        assert matched[0]["side"] == "long"
        assert missed == [{"price": 110.0, "side": "short"}]
        assert false_alarms == []

    def test_match_predictions_to_actuals_tracks_short_match_and_long_miss(self):
        """Matching should also cover the branch where only the short side is found."""
        predictions = [
            {"price": 120.0, "side": "short"},
        ]
        actuals = [
            {"price": 95.0, "side": "long"},
            {"price": 120.5, "side": "short"},
        ]

        tp, fp, fn, matched, missed, false_alarms = match_predictions_to_actuals(
            predictions,
            actuals,
            tolerance_pct=1.0,
        )

        assert tp == 1
        assert fp == 0
        assert fn == 1
        assert matched[0]["side"] == "short"
        assert missed == [{"price": 95.0, "side": "long"}]
        assert false_alarms == []


class TestRunBacktest:
    """Integration tests for backtest execution."""

    @pytest.mark.skip(reason="Requires database - run manually")
    def test_backtest_btc_2024(self):
        """Run backtest on BTC 2024 data."""
        config = BacktestConfig(
            symbol="BTCUSDT",
            start_date=datetime(2024, 6, 1),
            end_date=datetime(2024, 12, 31),
            tolerance_pct=1.0,
        )

        result = run_backtest(config)

        # Gate 2: F1 >= 0.6
        assert result.metrics.f1_score >= 0.4, (
            f"F1 score {result.metrics.f1_score} below minimum threshold"
        )

    def test_run_backtest_returns_error_when_database_missing(self, tmp_path):
        """Missing DB should return an errored result without attempting a connection."""
        config = BacktestConfig(
            symbol="BTCUSDT",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            db_path=str(tmp_path / "missing.duckdb"),
        )

        result = run_backtest(config)

        assert result.error.startswith("Database not found:")

    def test_run_backtest_returns_error_when_no_prediction_data(self, monkeypatch, tmp_path):
        """No timestamps should return a clean no-data error."""
        db_path = tmp_path / "present.duckdb"
        db_path.write_text("")
        conn = _SequenceConn([[]])

        monkeypatch.setattr(backtest.duckdb, "connect", lambda *args, **kwargs: conn)

        result = run_backtest(
            BacktestConfig(
                symbol="BTCUSDT",
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 2),
                db_path=str(db_path),
            )
        )

        assert result.error == "No prediction data found in specified period"
        assert conn.closed is True

    def test_run_backtest_aggregates_matches_and_verbose_output(
        self,
        monkeypatch,
        tmp_path,
        capsys,
    ):
        """Backtest should aggregate hourly results, skip empty predictions, and close the DB."""
        db_path = tmp_path / "present.duckdb"
        db_path.write_text("")
        timestamps = [
            (datetime(2024, 1, 1, 0, 0),),
            (datetime(2024, 1, 1, 1, 0),),
        ]
        conn = _SequenceConn([timestamps])
        prediction_calls = {"count": 0}

        def fake_get_predicted_zones(*args, **kwargs):
            prediction_calls["count"] += 1
            if prediction_calls["count"] == 1:
                return []
            return [{"price": 70000.0, "side": "long"}]

        def fake_get_actual_liquidations(*args, **kwargs):
            return [{"price": 70200.0, "side": "long"}, {"price": 75000.0, "side": "short"}]

        def fake_match_predictions_to_actuals(*args, **kwargs):
            return (
                1,
                0,
                1,
                [{"predicted": 70000.0, "actual": 70200.0, "side": "long", "error_pct": 0.28}],
                [{"price": 75000.0, "side": "short"}],
                [{"price": 80000.0, "side": "short"}] * 10,
            )

        monkeypatch.setattr(backtest.duckdb, "connect", lambda *args, **kwargs: conn)
        monkeypatch.setattr(backtest, "get_predicted_zones", fake_get_predicted_zones)
        monkeypatch.setattr(backtest, "get_actual_liquidations", fake_get_actual_liquidations)
        monkeypatch.setattr(backtest, "match_predictions_to_actuals", fake_match_predictions_to_actuals)

        result = run_backtest(
            BacktestConfig(
                symbol="BTCUSDT",
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 2),
                db_path=str(db_path),
            ),
            verbose=True,
        )

        assert result.true_positives == 1
        assert result.false_negatives == 1
        assert result.total_predictions == 1
        assert result.total_liquidations == 2
        assert result.snapshots_analyzed == 2
        assert result.processing_time_ms >= 0
        assert result.false_alarms == [{"price": 80000.0, "side": "short"}] * 5
        assert conn.closed is True
        assert "TP=1 FP=0 FN=1" in capsys.readouterr().out


class TestBacktestReport:
    @pytest.mark.parametrize(
        ("f1_score", "expected_status"),
        [
            (0.7, "✅ PASSED"),
            (0.5, "⚠️ ACCEPTABLE"),
            (0.2, "❌ FAILED"),
        ],
    )
    def test_generate_backtest_report_writes_gate_status(
        self,
        tmp_path,
        f1_score,
        expected_status,
    ):
        """Report generation should render markdown and the proper gate label."""
        result = BacktestResult(
            config=BacktestConfig(
                symbol="BTCUSDT",
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 31),
            ),
            metrics=PredictionMetrics(precision=f1_score, recall=f1_score, f1_score=f1_score),
            true_positives=5,
            false_positives=1,
            false_negatives=2,
            total_predictions=6,
            total_liquidations=7,
            snapshots_analyzed=3,
        )
        output_path = tmp_path / "reports" / "backtest.md"

        generate_backtest_report(result, output_path)

        report = output_path.read_text()
        assert output_path.exists()
        assert expected_status in report
        assert "# Backtest Report: BTCUSDT" in report
        assert "Gate 2 Decision" in report
