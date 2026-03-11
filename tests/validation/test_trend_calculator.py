"""
Tests for trend_calculator.py - Linear regression and trend analysis.

Tests cover:
- Slope calculation
- Trend direction determination
- Change percentage calculation
- Multi-metric trend analysis
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.validation.trends.trend_calculator import (
    TrendCalculator,
    TrendDirection,
    get_trend_calculator,
)


@dataclass
class _GradeValue:
    value: str


@dataclass
class _ValidationRun:
    started_at: datetime
    overall_score: float | None = None
    overall_grade: _GradeValue | None = None


class TestTrendCalculator:
    """Test TrendCalculator functionality."""

    def test_calculate_score_trend_with_improving_scores(self):
        """Trend should be IMPROVING when scores increase."""
        # Arrange
        calculator = TrendCalculator(min_data_points=3)

        start = datetime.utcnow() - timedelta(days=10)
        scores = [
            (start + timedelta(days=i), 70.0 + i * 2.0)  # Scores: 70, 72, 74, 76, 78
            for i in range(5)
        ]

        # Act
        trend = calculator.calculate_score_trend(scores)

        # Assert
        assert trend["direction"] == TrendDirection.IMPROVING
        assert trend["slope"] > 0

    def test_calculate_score_trend_with_degrading_scores(self):
        """Trend should be DEGRADING when scores decrease."""
        # Arrange
        calculator = TrendCalculator(min_data_points=3)

        start = datetime.utcnow() - timedelta(days=10)
        scores = [
            (start + timedelta(days=i), 90.0 - i * 3.0)  # Scores: 90, 87, 84, 81, 78
            for i in range(5)
        ]

        # Act
        trend = calculator.calculate_score_trend(scores)

        # Assert
        assert trend["direction"] == TrendDirection.DEGRADING
        assert trend["slope"] < 0

    def test_calculate_score_trend_with_stable_scores(self):
        """Trend should be STABLE when scores don't change significantly."""
        # Arrange
        calculator = TrendCalculator()

        start = datetime.utcnow() - timedelta(days=10)
        scores = [
            (start + timedelta(days=i), 85.0 + (i % 2) * 0.5)  # Scores oscillate slightly around 85
            for i in range(10)
        ]

        # Act
        trend = calculator.calculate_score_trend(scores)

        # Assert
        assert trend["direction"] == TrendDirection.STABLE

    def test_calculate_score_trend_with_insufficient_data(self):
        """Trend should be INSUFFICIENT_DATA with too few points."""
        # Arrange
        calculator = TrendCalculator(min_data_points=5)

        scores = [
            (datetime.utcnow(), 80.0),
            (datetime.utcnow() + timedelta(days=1), 82.0),
        ]  # Only 2 points

        # Act
        trend = calculator.calculate_score_trend(scores)

        # Assert
        assert trend["direction"] == TrendDirection.INSUFFICIENT_DATA

    def test_slope_calculation_accuracy(self):
        """Slope should be calculated accurately."""
        # Arrange
        calculator = TrendCalculator()

        start = datetime.utcnow()
        # Perfect linear increase: 2 points per day
        scores = [(start + timedelta(days=i), 50.0 + i * 2.0) for i in range(10)]

        # Act
        trend = calculator.calculate_score_trend(scores)

        # Assert
        # Slope should be approximately 2.0 (2 points per day)
        assert abs(trend["slope"] - 2.0) < 0.1  # Allow small numerical error

    def test_change_percent_calculation(self):
        """Change percent should be calculated correctly."""
        # Arrange
        calculator = TrendCalculator(min_data_points=2)

        start = datetime.utcnow()
        scores = [
            (start, 80.0),
            (start + timedelta(days=1), 90.0),
            (start + timedelta(days=2), 100.0),
        ]

        # Act
        trend = calculator.calculate_score_trend(scores)

        # Assert
        # (100 - 80) / 80 * 100 = 25%
        assert abs(trend["change_percent"] - 25.0) < 0.1

    def test_trend_includes_first_and_last_scores(self):
        """Trend should include first and last scores."""
        # Arrange
        calculator = TrendCalculator(min_data_points=2)

        scores = [
            (datetime.utcnow(), 70.0),
            (datetime.utcnow() + timedelta(days=5), 90.0),
        ]

        # Act
        trend = calculator.calculate_score_trend(scores)

        # Assert
        assert trend["first_score"] == 70.0
        assert trend["last_score"] == 90.0

    def test_calculate_score_trend_uses_zero_change_percent_when_baseline_is_zero(self):
        """Zero first score should not trigger division-by-zero."""
        calculator = TrendCalculator(min_data_points=2)
        start = datetime.utcnow()

        trend = calculator.calculate_score_trend(
            [
                (start, 0.0),
                (start + timedelta(days=1), 10.0),
            ]
        )

        assert trend["change_percent"] == 0
        assert trend["direction"] == TrendDirection.STABLE

    def test_calculate_test_trend_includes_test_type(self):
        """Specific test trend should preserve the test type label."""
        calculator = TrendCalculator(min_data_points=2)
        start = datetime.utcnow()

        trend = calculator.calculate_test_trend(
            "ocr",
            [
                (start, 70.0),
                (start + timedelta(days=1), 80.0),
            ],
        )

        assert trend["test_type"] == "ocr"
        assert trend["direction"] == TrendDirection.IMPROVING

    def test_calculate_grade_trend_reports_distribution_and_direction(self):
        """Grade trend should translate grades, count them, and detect direction."""
        calculator = TrendCalculator(min_data_points=3)
        start = datetime.utcnow() - timedelta(days=3)

        trend = calculator.calculate_grade_trend(
            [
                (start, "C"),
                (start + timedelta(days=1), "B"),
                (start + timedelta(days=2), "A"),
            ]
        )

        assert trend["direction"] == TrendDirection.IMPROVING
        assert trend["most_common_grade"] in {"A", "B", "C"}
        assert trend["grade_distribution"] == {"C": 1, "B": 1, "A": 1}
        assert trend["first_grade"] == "C"
        assert trend["last_grade"] == "A"

    def test_calculate_grade_trend_can_report_degrading_and_stable(self):
        """Grade trend should cover both degrading and stable branches."""
        calculator = TrendCalculator(min_data_points=3)
        start = datetime.utcnow() - timedelta(days=3)

        degrading = calculator.calculate_grade_trend(
            [
                (start, "A"),
                (start + timedelta(days=1), "B"),
                (start + timedelta(days=2), "F"),
            ]
        )
        stable = calculator.calculate_grade_trend(
            [
                (start, "B"),
                (start + timedelta(days=1), "B"),
                (start + timedelta(days=2), "B"),
            ]
        )

        assert degrading["direction"] == TrendDirection.DEGRADING
        assert stable["direction"] == TrendDirection.STABLE

    def test_calculate_grade_trend_returns_insufficient_data(self):
        """Grade trend should short-circuit when too few grade points exist."""
        calculator = TrendCalculator(min_data_points=3)

        trend = calculator.calculate_grade_trend([(datetime.utcnow(), "A")])

        assert trend == {
            "direction": TrendDirection.INSUFFICIENT_DATA,
            "data_points": 1,
        }

    def test_calculate_multi_metric_trends_aggregates_scores_and_grades(self):
        """Multi-metric trend calculation should aggregate both score and grade series."""
        calculator = TrendCalculator(min_data_points=2)
        start = datetime.utcnow() - timedelta(days=2)
        runs = [
            _ValidationRun(start, overall_score=70.0, overall_grade=_GradeValue("C")),
            _ValidationRun(
                start + timedelta(days=1),
                overall_score=80.0,
                overall_grade=_GradeValue("B"),
            ),
            _ValidationRun(
                start + timedelta(days=2),
                overall_score=90.0,
                overall_grade=_GradeValue("A"),
            ),
        ]

        trends = calculator.calculate_multi_metric_trends(runs)

        assert set(trends) == {"overall_score", "overall_grade"}
        assert trends["overall_score"]["direction"] == TrendDirection.IMPROVING
        assert trends["overall_grade"]["direction"] == TrendDirection.IMPROVING

    def test_calculate_slope_returns_zero_when_timestamps_are_identical(self):
        """Slope should be zero when the x-axis has no spread."""
        calculator = TrendCalculator()
        ts = datetime.utcnow()

        slope = calculator._calculate_slope(
            [
                (ts, 70.0),
                (ts, 90.0),
            ]
        )

        assert slope == 0.0

    def test_calculate_slope_returns_zero_for_single_point(self):
        """Slope should be zero when fewer than two points exist."""
        calculator = TrendCalculator()

        slope = calculator._calculate_slope([(datetime.utcnow(), 70.0)])

        assert slope == 0.0

    def test_get_trend_calculator_returns_singleton(self):
        """get_trend_calculator should return same instance."""
        # Act
        calc1 = get_trend_calculator()
        calc2 = get_trend_calculator()

        # Assert
        assert calc1 is calc2


class TestTrendDirection:
    """Test TrendDirection enum."""

    def test_trend_direction_values(self):
        """TrendDirection should have expected values."""
        # Assert
        assert TrendDirection.IMPROVING == "improving"
        assert TrendDirection.STABLE == "stable"
        assert TrendDirection.DEGRADING == "degrading"
        assert TrendDirection.INSUFFICIENT_DATA == "insufficient_data"
