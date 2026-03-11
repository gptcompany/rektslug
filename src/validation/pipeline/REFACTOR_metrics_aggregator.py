"""REFACTORED Metrics aggregator for validation dashboard.

Implements structural refactoring for 100% testability:
1. De-coupled database connection (Dependency Injection)
2. Pure logic extraction for alert generation and status determination
3. Consistent timestamp handling
"""

import math
import logging
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any, Protocol

from src.validation.pipeline.models import (
    Alert,
    DashboardMetrics,
    TrendDataPoint,
    compute_overall_grade,
    determine_dashboard_status,
)

logger = logging.getLogger(__name__)

class DatabaseConnection(Protocol):
    """Protocol for database connection to allow easy mocking."""
    def execute(self, query: str, parameters: Optional[List[Any]] = None) -> Any: ...
    def close(self) -> None: ...

class MetricsAggregator:
    """Aggregates validation metrics with testable pure logic."""

    def __init__(self, db_conn: Optional[DatabaseConnection] = None):
        """Initialize with optional connection."""
        self.conn = db_conn

    def get_dashboard_metrics(
        self,
        symbol: str = "BTCUSDT",
        days: int = 30,
        conn_override: Optional[DatabaseConnection] = None
    ) -> Optional[DashboardMetrics]:
        """Get aggregated metrics using injected connection."""
        conn = conn_override or self.conn
        if not conn:
            logger.error("No database connection provided to MetricsAggregator")
            return None

        # 1. Fetch Data (IO)
        latest_data = self._fetch_latest_validation(conn, symbol)
        if not latest_data:
            return None

        trend_data = self._fetch_trend_data(conn, symbol, days)

        # 2. Process Metrics (Pure Logic)
        return self.compute_dashboard_metrics(latest_data, trend_data)

    def compute_dashboard_metrics(
        self, 
        latest: Dict[str, Any], 
        trend: List[TrendDataPoint],
        now_override: Optional[datetime] = None
    ) -> DashboardMetrics:
        """PURE LOGIC: Compute dashboard metrics from raw data dictionary."""
        now = now_override or datetime.now()
        
        # Consistent timestamp handling
        timestamp = latest["timestamp"]
        if isinstance(timestamp, date) and not isinstance(timestamp, datetime):
            timestamp = datetime.combine(timestamp, datetime.min.time())
        
        days_since = (now - timestamp).days
        f1_score = latest.get("f1_score", 0.0) or 0.0
        
        # Sanitize F1
        if math.isnan(f1_score) or math.isinf(f1_score):
            f1_score = 0.0

        # Generate Alerts
        alerts = self.generate_alerts(latest, trend, now)
        
        # Determine Status
        status = determine_dashboard_status(f1_score, days_since)

        return DashboardMetrics(
            status=status,
            last_validation_timestamp=latest["timestamp"],
            last_validation_grade=compute_overall_grade(f1_score),
            f1_score=f1_score,
            precision=latest.get("precision", 0.0),
            recall=latest.get("recall", 0.0),
            trend=trend,
            alerts=alerts,
            backtest_coverage=latest.get("snapshots_analyzed", 0),
            backtest_period_days=latest.get("period_days", 0),
        )

    def generate_alerts(
        self,
        latest: Dict[str, Any],
        trend: List[TrendDataPoint],
        now: datetime
    ) -> List[Alert]:
        """PURE LOGIC: Generate alerts based on thresholds and trends."""
        alerts = []
        
        # 1. Stale data check
        timestamp = latest["timestamp"]
        if isinstance(timestamp, date) and not isinstance(timestamp, datetime):
            timestamp = datetime.combine(timestamp, datetime.min.time())
        
        days_since = (now - timestamp).days
        if days_since > 14:
            alerts.append(Alert(level="error", message=f"Validation data is {days_since} days old. Run validation pipeline.", timestamp=now))
        elif days_since > 7:
            alerts.append(Alert(level="warning", message=f"Validation data is {days_since} days old. Consider running validation.", timestamp=now))

        # 2. F1 Threshold checks
        f1 = latest.get("f1_score")
        if f1 is None or math.isnan(f1) or math.isinf(f1):
            alerts.append(Alert(level="error", message="F1 score is invalid (missing or corrupt data).", timestamp=now))
        elif f1 < 0.4:
            alerts.append(Alert(level="error", message=f"F1 score ({f1:.1%}) is below critical threshold (40%).", timestamp=now))
        elif f1 < 0.6:
            alerts.append(Alert(level="warning", message=f"F1 score ({f1:.1%}) is below target threshold (60%).", timestamp=now))

        # 3. Trend degradation check
        if len(trend) >= 3:
            recent_f1 = [t.f1_score for t in trend[-3:]]
            valid_f1 = [f for f in recent_f1 if f is not None and not math.isnan(f)]
            if len(valid_f1) >= 3:
                # Strictly decreasing check
                if all(valid_f1[i] > valid_f1[i + 1] for i in range(len(valid_f1) - 1)):
                    alerts.append(Alert(level="warning", message="F1 score has declined for 3 consecutive measurements.", timestamp=now))

        return alerts

    def _fetch_latest_validation(self, conn: DatabaseConnection, symbol: str) -> Optional[Dict[str, Any]]:
        """IO: Fetch latest validation from DB."""
        try:
            res = conn.execute("""
                SELECT created_at, f1_score, precision, recall, snapshots_analyzed, 
                       DATEDIFF('day', start_date, end_date) as period_days
                FROM validation_backtest_results WHERE symbol = ? ORDER BY created_at DESC LIMIT 1
            """, [symbol]).fetchone()
            
            if res:
                return {
                    "timestamp": res[0],
                    "f1_score": float(res[1]) if res[1] else 0.0,
                    "precision": float(res[2]) if res[2] else 0.0,
                    "recall": float(res[3]) if res[3] else 0.0,
                    "snapshots_analyzed": res[4] or 0,
                    "period_days": res[5] or 0,
                }
        except:
            pass
        return None

    def _fetch_trend_data(self, conn: DatabaseConnection, symbol: str, days: int) -> List[TrendDataPoint]:
        """IO: Fetch trend data from DB."""
        trend = []
        cutoff = datetime.now() - timedelta(days=days)
        try:
            res = conn.execute("""
                SELECT date, 
                       MAX(CASE WHEN metric_type = 'f1_score' THEN value END) as f1,
                       MAX(CASE WHEN metric_type = 'precision' THEN value END) as precision,
                       MAX(CASE WHEN metric_type = 'recall' THEN value END) as recall
                FROM validation_metrics_history
                WHERE symbol = ? AND date >= ?
                GROUP BY date ORDER BY date
            """, [symbol, cutoff.date()]).fetchall()
            
            for row in res:
                trend.append(TrendDataPoint(
                    date=row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                    f1_score=float(row[1]) if row[1] else 0.0,
                    precision=float(row[2]) if row[2] else None,
                    recall=float(row[3]) if row[3] else None,
                ))
        except:
            pass
        return trend
