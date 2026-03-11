"""Unit tests for degradation detector refactor-compatible seams."""

import pytest
from datetime import datetime, timedelta
from src.validation.trends.degradation_detector import DegradationDetector, DegradationSeverity

class TestREFACTORDegradationDetector:
    def test_analyze_score_trend_stable(self):
        """Should detect no degradation when scores are stable."""
        detector = DegradationDetector(lookback_days=7)
        now = datetime(2024, 1, 10)
        
        # Baseline: 90, Recent: 88 (drop 2.2%, below minor threshold of 5%)
        scores = [
            (datetime(2024, 1, 1), 90.0),
            (datetime(2024, 1, 2), 90.0),
            (datetime(2024, 1, 9), 88.0),
            (datetime(2024, 1, 10), 88.0),
        ]
        
        result = detector.analyze_score_trend(scores, now_override=now)
        assert result["degradation_detected"] is False
        assert result["severity"] == DegradationSeverity.NONE

    def test_analyze_score_trend_critical(self):
        """Should detect critical degradation for large drops."""
        detector = DegradationDetector(lookback_days=7, critical_threshold=25.0)
        now = datetime(2024, 1, 10)
        
        # Baseline: 100, Recent: 70 (drop 30%)
        scores = [
            (datetime(2024, 1, 1), 100.0),
            (datetime(2024, 1, 9), 70.0),
        ]
        
        result = detector.analyze_score_trend(scores, now_override=now)
        assert result["degradation_detected"] is True
        assert result["severity"] == DegradationSeverity.CRITICAL
        assert result["degradation_percent"] == 30.0

    def test_analyze_grade_trend_f_increase(self):
        """Should detect severe degradation if F grades increase significantly."""
        detector = DegradationDetector(lookback_days=7)
        now = datetime(2024, 1, 10)
        
        # Baseline: 10 A, 0 F
        # Recent: 5 A, 5 F (F pct increased by 50%)
        grades = []
        for i in range(1, 11):
            grades.append((datetime(2024, 1, 1), "A"))
        for i in range(1, 6):
            grades.append((datetime(2024, 1, 9), "A"))
            grades.append((datetime(2024, 1, 9), "F"))
            
        result = detector.analyze_grade_trend(grades, now_override=now)
        assert result["degradation_detected"] is True
        assert result["severity"] == DegradationSeverity.SEVERE
        assert result["recent_f_pct"] == 50.0

    def test_analyze_multi_metric_worst_severity(self):
        """Should correctly pick the worst severity across metrics."""
        detector = DegradationDetector(lookback_days=7)
        now = datetime(2024, 1, 10)
        
        # Run 1: Good
        # Run 2: Critical score drop
        run_data = [
            {"started_at": datetime(2024, 1, 1), "overall_score": 95.0, "overall_grade": "A"},
            {"started_at": datetime(2024, 1, 9), "overall_score": 50.0, "overall_grade": "C"},
        ]
        
        result = detector.analyze_multi_metric(run_data, now_override=now)
        assert result["summary"]["any_degradation"] is True
        assert result["summary"]["worst_severity"] == DegradationSeverity.CRITICAL

    def test_insufficient_data(self):
        """Should handle cases with not enough data."""
        detector = DegradationDetector()
        assert detector.analyze_score_trend([(datetime.now(), 100.0)])["degradation_detected"] is False
        assert detector.analyze_grade_trend([])["degradation_detected"] is False
