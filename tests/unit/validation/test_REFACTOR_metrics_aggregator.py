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

    def test_generate_alerts_invalid_f1(self):
        """Should generate alert for NaN/Inf/None F1 score."""
        aggregator = MetricsAggregator()
        now = datetime(2024, 1, 20)
        
        for val in [None, float('nan'), float('inf')]:
            latest = {"timestamp": now, "f1_score": val}
            alerts = aggregator.generate_alerts(latest, [], now)
            assert any("invalid" in a.message for a in alerts)

    def test_compute_dashboard_metrics_with_date(self):
        """Should handle date (instead of datetime) in latest dict."""
        aggregator = MetricsAggregator()
        now = datetime(2024, 1, 20, 12, 0, 0)
        latest = {
            "timestamp": date(2024, 1, 19),
            "f1_score": 0.8,
            "precision": 0.8,
            "recall": 0.8
        }
        metrics = aggregator.compute_dashboard_metrics(latest, [], now_override=now)
        assert metrics.last_validation_timestamp == date(2024, 1, 19)

    def test_get_latest_validation_fallback(self):
        """Should fall back to liquidation_snapshots if validation_backtest_results fails."""
        mock_conn = MagicMock()
        # First call fails (CatalogException - table doesn't exist)
        # Second call succeeds
        import src.validation.pipeline.metrics_aggregator
        from src.validation.pipeline.metrics_aggregator import duckdb as real_duckdb
        
        # If duckdb is mocked as None in sys.modules, we need to handle that
        # In our current setup duckdb is a MagicMock from the conftest try-except or the runner
        
        exc = getattr(real_duckdb, 'CatalogException', Exception)
        
        def execute_side_effect(query, *args):
            if "validation_backtest_results" in query:
                raise exc("Table not found")
            m = MagicMock()
            m.fetchone.return_value = (datetime(2024, 1, 20), 100, 7)
            return m

        mock_conn.execute.side_effect = execute_side_effect
        
        aggregator = MetricsAggregator()
        result = aggregator._get_latest_validation(mock_conn, "BTCUSDT")
        
        assert result is not None
        assert result["snapshots_analyzed"] == 100
        assert result["f1_score"] == 0.0 # Fallback default

    def test_get_trend_data_fallback(self):
        """Should fall back to validation_backtest_results if history table fails."""
        mock_conn = MagicMock()
        import src.validation.pipeline.metrics_aggregator
        from src.validation.pipeline.metrics_aggregator import duckdb as real_duckdb
        exc = getattr(real_duckdb, 'CatalogException', Exception)

        def execute_side_effect(query, *args):
            if "validation_metrics_history" in query:
                raise exc("Table not found")
            m = MagicMock()
            m.fetchall.return_value = [(date(2024, 1, 19), 0.8, 0.8, 0.8)]
            return m

        mock_conn.execute.side_effect = execute_side_effect
        aggregator = MetricsAggregator()
        trend = aggregator._get_trend_data(mock_conn, "BTCUSDT", 7)
        
        assert len(trend) == 1
        assert trend[0].f1_score == 0.8

    def test_save_metrics_to_history(self):
        """Should execute CREATE and INSERT queries."""
        mock_conn = MagicMock()
        aggregator = MetricsAggregator()
        
        aggregator.save_metrics_to_history(
            mock_conn, "BTCUSDT", datetime(2024, 1, 20), 0.8, 0.8, 0.8
        )
        
        assert mock_conn.execute.call_count >= 2 # CREATE + 3 INSERTS actually

    def test_generate_alerts_warnings(self):
        """Should generate warning alerts for moderate stale data or F1."""
        aggregator = MetricsAggregator()
        now = datetime(2024, 1, 20)
        # 10 days old (7 < 10 <= 14) -> warning
        # F1 = 0.5 (0.4 <= 0.5 < 0.6) -> warning
        latest = {"timestamp": now - timedelta(days=10), "f1_score": 0.5}
        
        alerts = aggregator.generate_alerts(latest, [], now)
        
        assert len(alerts) == 2
        assert all(a.level == "warning" for a in alerts)
        assert any("10 days old" in a.message for a in alerts)
        assert any("below target threshold" in a.message for a in alerts)

    def test_generate_alerts_alias(self):
        """Should cover the _generate_alerts wrapper."""
        aggregator = MetricsAggregator()
        latest = {"timestamp": datetime.now(), "f1_score": 0.8}
        alerts = aggregator._generate_alerts(latest, [])
        assert isinstance(alerts, list)

    def test_get_dashboard_metrics_no_conn_no_file(self, tmp_path):
        """Should return None if no connection and DB file doesn't exist."""
        db_path = str(tmp_path / "nonexistent.duckdb")
        aggregator = MetricsAggregator(db_path=db_path)
        assert aggregator.get_dashboard_metrics() is None

    def test_get_dashboard_metrics_latest_none(self):
        """Should return None if _fetch_latest_validation returns None."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        aggregator = MetricsAggregator(db_conn=mock_conn)
        assert aggregator.get_dashboard_metrics() is None

    def test_compute_dashboard_metrics_missing_f1(self):
        """Should handle missing F1 by defaulting to 0.0 (line 111)."""
        aggregator = MetricsAggregator()
        latest = {"timestamp": datetime.now(), "precision": 0.8} # f1_score missing
        metrics = aggregator.compute_dashboard_metrics(latest, [])
        assert metrics.f1_score == 0.0

    def test_get_trend_data_history_success(self):
        """Should cover line 241 by successfully fetching from history table."""
        mock_conn = MagicMock()
        # Mock history table results
        mock_conn.execute.return_value.fetchall.return_value = [
            (date(2024, 1, 19), 0.8, 0.8, 0.8)
        ]
        aggregator = MetricsAggregator()
        trend = aggregator._get_trend_data(mock_conn, "BTCUSDT", 7)
        assert len(trend) == 1
        assert trend[0].f1_score == 0.8
        assert trend[0].date == "2024-01-19"

    def test_get_dashboard_metrics_helper(self, tmp_path):
        """Should cover the module-level helper function."""
        from src.validation.pipeline.metrics_aggregator import get_dashboard_metrics
        db_path = str(tmp_path / "nonexistent.duckdb")
        assert get_dashboard_metrics(db_path=db_path) is None
