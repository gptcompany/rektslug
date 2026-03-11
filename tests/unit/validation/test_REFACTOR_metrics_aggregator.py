"""Unit tests for metrics aggregator refactor-compatible seams."""

from datetime import datetime, timedelta, date
from unittest.mock import MagicMock
from src.validation.pipeline.metrics_aggregator import MetricsAggregator, DatabaseConnection
from src.validation.pipeline.models import TrendDataPoint

class TestREFACTORMetricsAggregator:
    def test_compute_dashboard_metrics_success(self):
        """Should correctly aggregate latest data and trend into metrics."""
        aggregator = MetricsAggregator()
        now = datetime(2024, 1, 20, 12, 0, 0)
        
        latest = {
            "timestamp": now - timedelta(days=1),
            "f1_score": 0.85,
            "precision": 0.80,
            "recall": 0.90,
            "snapshots_analyzed": 100,
            "period_days": 30
        }
        
        trend = [
            TrendDataPoint(date="2024-01-18", f1_score=0.80),
            TrendDataPoint(date="2024-01-19", f1_score=0.82),
            TrendDataPoint(date="2024-01-20", f1_score=0.85),
        ]
        
        metrics = aggregator.compute_dashboard_metrics(latest, trend, now_override=now)
        
        assert metrics.f1_score == 0.85
        assert metrics.last_validation_grade == "A"
        assert len(metrics.alerts) == 0
        assert metrics.backtest_coverage == 100

    def test_generate_alerts_stale_data(self):
        """Should generate error alert for data > 14 days old."""
        aggregator = MetricsAggregator()
        now = datetime(2024, 1, 20)
        latest = {"timestamp": now - timedelta(days=15), "f1_score": 0.8}
        
        alerts = aggregator.generate_alerts(latest, [], now)
        
        assert len(alerts) == 1
        assert alerts[0].level == "error"
        assert "15 days old" in alerts[0].message

    def test_generate_alerts_low_f1(self):
        """Should generate error alert for F1 < 0.4."""
        aggregator = MetricsAggregator()
        now = datetime(2024, 1, 20)
        latest = {"timestamp": now, "f1_score": 0.35}
        
        alerts = aggregator.generate_alerts(latest, [], now)
        
        assert len(alerts) == 1
        assert alerts[0].level == "error"
        assert "below critical threshold" in alerts[0].message

    def test_generate_alerts_declining_trend(self):
        """Should generate warning alert for 3 consecutive declines."""
        aggregator = MetricsAggregator()
        now = datetime(2024, 1, 20)
        latest = {"timestamp": now, "f1_score": 0.7}
        
        trend = [
            TrendDataPoint(date="2024-01-18", f1_score=0.9),
            TrendDataPoint(date="2024-01-19", f1_score=0.8),
            TrendDataPoint(date="2024-01-20", f1_score=0.7),
        ]
        
        alerts = aggregator.generate_alerts(latest, trend, now)
        
        assert any(a.level == "warning" and "declined" in a.message for a in alerts)

    def test_fetch_methods_error_handling(self):
        """Should handle database errors gracefully by returning empty/None."""
        mock_conn = MagicMock(spec=DatabaseConnection)
        mock_conn.execute.side_effect = Exception("DB Crash")
        
        aggregator = MetricsAggregator()
        
        assert aggregator._fetch_latest_validation(mock_conn, "BTCUSDT") is None
        assert aggregator._fetch_trend_data(mock_conn, "BTCUSDT", 30) == []

    def test_get_dashboard_metrics_integration(self):
        """Should coordinate fetch and compute."""
        mock_conn = MagicMock(spec=DatabaseConnection)
        # Mock latest validation
        mock_conn.execute.return_value.fetchone.return_value = (
            datetime.now(), 0.8, 0.8, 0.8, 50, 7
        )
        # Mock trend data (empty fetchall)
        mock_conn.execute.return_value.fetchall.return_value = []
        
        aggregator = MetricsAggregator(db_conn=mock_conn)
        res = aggregator.get_dashboard_metrics("BTCUSDT")
        
        assert res is not None
        assert res.f1_score == 0.8
        assert mock_conn.execute.call_count >= 1
