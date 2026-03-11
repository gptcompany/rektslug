"""Metrics aggregator for validation dashboard.

Aggregates validation results into dashboard-friendly format
per specs/014-validation-pipeline/data-model.md.
"""

import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

try:
    import duckdb
    DuckDBConn = duckdb.DuckDBPyConnection
except (ImportError, AttributeError):
    duckdb = None
    DuckDBConn = Any  # type: ignore

from src.validation.pipeline.models import (
    Alert,
    DashboardMetrics,
    TrendDataPoint,
    compute_overall_grade,
    determine_dashboard_status,
)


class DatabaseConnection(Protocol):
    """Lightweight database protocol for testing and dependency injection."""

    def execute(self, query: str, parameters: list[Any] | None = None) -> Any: ...

    def close(self) -> None: ...


class MetricsAggregator:
    """Aggregates validation metrics for dashboard display.

    Responsibilities:
    - Query historical validation results
    - Compute trend data for charts
    - Generate alerts based on thresholds
    - Provide dashboard-ready metrics
    """

    def __init__(
        self,
        db_path: str = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        db_conn: Any = None,
    ):
        """Initialize aggregator.

        Args:
            db_path: Path to DuckDB database with validation results
        """
        self.db_path = db_path
        self._db_conn = db_conn

    def get_dashboard_metrics(
        self,
        symbol: str = "BTCUSDT",
        days: int = 30,
        conn_override: Any = None,
    ) -> DashboardMetrics | None:
        """Get aggregated metrics for dashboard display.

        Args:
            symbol: Trading pair to get metrics for
            days: Number of days for trend data

        Returns:
            DashboardMetrics or None if no data
        """
        owns_connection = False
        conn = conn_override or self._db_conn
        if conn is None:
            if not Path(self.db_path).exists():
                return None
            conn = duckdb.connect(self.db_path, read_only=True)
            owns_connection = True

        try:
            # Get latest validation result
            latest = self._fetch_latest_validation(conn, symbol)
            if latest is None:
                return None

            # Get trend data
            trend = self._fetch_trend_data(conn, symbol, days)
            return self.compute_dashboard_metrics(latest, trend)

        finally:
            if owns_connection:
                conn.close()

    def compute_dashboard_metrics(
        self,
        latest: dict[str, Any],
        trend: list[TrendDataPoint],
        now_override: datetime | None = None,
    ) -> DashboardMetrics:
        """Compute dashboard metrics from already-fetched data."""
        now = now_override or datetime.now()
        timestamp = latest["timestamp"]
        if isinstance(timestamp, date) and not isinstance(timestamp, datetime):
            timestamp = datetime.combine(timestamp, datetime.min.time())

        days_since = (now - timestamp).days
        f1_for_grade = latest.get("f1_score")
        if f1_for_grade is None or math.isnan(f1_for_grade) or math.isinf(f1_for_grade):
            f1_for_grade = 0.0

        alerts = self.generate_alerts(latest, trend, now)
        status = determine_dashboard_status(f1_for_grade, days_since)

        return DashboardMetrics(
            status=status,
            last_validation_timestamp=latest["timestamp"],
            last_validation_grade=compute_overall_grade(f1_for_grade),
            f1_score=f1_for_grade,
            precision=latest.get("precision", 0.0),
            recall=latest.get("recall", 0.0),
            trend=trend,
            alerts=alerts,
            backtest_coverage=latest.get("snapshots_analyzed", 0),
            backtest_period_days=latest.get("period_days", 0),
        )

    def _get_latest_validation(self, conn: DuckDBConn, symbol: str) -> dict | None:
        """Get most recent validation result.

        Tries validation_backtest_results first, falls back to
        reconstructing from liquidation_snapshots if needed.
        """
        # Try validation_backtest_results table first
        try:
            result = conn.execute(
                """
                SELECT
                    created_at as timestamp,
                    f1_score,
                    precision,
                    recall,
                    snapshots_analyzed,
                    DATEDIFF('day', start_date, end_date) as period_days
                FROM validation_backtest_results
                WHERE symbol = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [symbol],
            ).fetchone()

            if result:
                return {
                    "timestamp": result[0],
                    "f1_score": float(result[1]) if result[1] else 0.0,
                    "precision": float(result[2]) if result[2] else 0.0,
                    "recall": float(result[3]) if result[3] else 0.0,
                    "snapshots_analyzed": result[4] or 0,
                    "period_days": result[5] or 0,
                }
        except (duckdb.CatalogException if duckdb else Exception):
            # Table doesn't exist yet
            pass

        # Fallback: estimate from liquidation_snapshots
        try:
            result = conn.execute(
                """
                SELECT
                    MAX(timestamp) as latest,
                    COUNT(DISTINCT DATE_TRUNC('hour', timestamp)) as snapshots,
                    DATEDIFF('day', MIN(timestamp), MAX(timestamp)) as days
                FROM liquidation_snapshots
                WHERE symbol = ?
                """,
                [symbol],
            ).fetchone()

            if result and result[0]:
                # Return placeholder metrics - actual validation not run
                return {
                    "timestamp": result[0],
                    "f1_score": 0.0,  # Unknown - validation not run
                    "precision": 0.0,
                    "recall": 0.0,
                    "snapshots_analyzed": result[1] or 0,
                    "period_days": result[2] or 0,
                }
        except (duckdb.CatalogException if duckdb else Exception):
            pass

        return None

    def _fetch_latest_validation(self, conn: DuckDBConn, symbol: str) -> dict | None:
        """Compatibility alias with a less DB-specific name."""
        try:
            return self._get_latest_validation(conn, symbol)
        except Exception:
            return None

    def _get_trend_data(
        self,
        conn: DuckDBConn,
        symbol: str,
        days: int,
    ) -> list[TrendDataPoint]:
        """Get historical trend data for chart.

        Args:
            conn: DuckDB connection
            symbol: Trading pair
            days: Number of days of history

        Returns:
            List of TrendDataPoint for chart
        """
        trend = []

        # Try validation_metrics_history table
        try:
            cutoff = datetime.now() - timedelta(days=days)
            result = conn.execute(
                """
                SELECT
                    date,
                    MAX(CASE WHEN metric_type = 'f1_score' THEN value END) as f1,
                    MAX(CASE WHEN metric_type = 'precision' THEN value END) as precision,
                    MAX(CASE WHEN metric_type = 'recall' THEN value END) as recall
                FROM validation_metrics_history
                WHERE symbol = ?
                  AND date >= ?
                GROUP BY date
                ORDER BY date
                """,
                [symbol, cutoff.date()],
            ).fetchall()

            for row in result:
                trend.append(
                    TrendDataPoint(
                        date=row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                        f1_score=float(row[1]) if row[1] else 0.0,
                        precision=float(row[2]) if row[2] else None,
                        recall=float(row[3]) if row[3] else None,
                    )
                )
        except (duckdb.CatalogException if duckdb else Exception):
            # Table doesn't exist - return empty trend
            pass

        # If no trend data, try validation_backtest_results
        if not trend:
            try:
                cutoff = datetime.now() - timedelta(days=days)
                result = conn.execute(
                    """
                    SELECT
                        DATE(created_at) as date,
                        f1_score,
                        precision,
                        recall
                    FROM validation_backtest_results
                    WHERE symbol = ?
                      AND created_at >= ?
                    ORDER BY created_at
                    """,
                    [symbol, cutoff],
                ).fetchall()

                for row in result:
                    trend.append(
                        TrendDataPoint(
                            date=row[0].isoformat()
                            if hasattr(row[0], "isoformat")
                            else str(row[0]),
                            f1_score=float(row[1]) if row[1] else 0.0,
                            precision=float(row[2]) if row[2] else None,
                            recall=float(row[3]) if row[3] else None,
                        )
                    )
            except (duckdb.CatalogException if duckdb else Exception):
                pass

        return trend

    def _fetch_trend_data(
        self,
        conn: DuckDBConn,
        symbol: str,
        days: int,
    ) -> list[TrendDataPoint]:
        """Compatibility alias with a less DB-specific name."""
        try:
            return self._get_trend_data(conn, symbol, days)
        except Exception:
            return []

    def generate_alerts(
        self,
        latest: dict,
        trend: list[TrendDataPoint],
        now: datetime,
    ) -> list[Alert]:
        """Pure alert generation logic for testability."""
        alerts = []

        timestamp = latest["timestamp"]
        if isinstance(timestamp, date) and not isinstance(timestamp, datetime):
            timestamp = datetime.combine(timestamp, datetime.min.time())
        days_since = (now - timestamp).days
        if days_since > 14:
            alerts.append(
                Alert(
                    level="error",
                    message=f"Validation data is {days_since} days old. Run validation pipeline.",
                    timestamp=now,
                )
            )
        elif days_since > 7:
            alerts.append(
                Alert(
                    level="warning",
                    message=f"Validation data is {days_since} days old. "
                    "Consider running validation.",
                    timestamp=now,
                )
            )

        f1 = latest.get("f1_score")
        if f1 is None or math.isnan(f1) or math.isinf(f1):
            alerts.append(
                Alert(
                    level="error",
                    message="F1 score is invalid (missing or corrupt data). "
                    "Check validation pipeline and data sources.",
                    timestamp=now,
                )
            )
        elif f1 < 0.4:
            alerts.append(
                Alert(
                    level="error",
                    message=f"F1 score ({f1:.1%}) is below critical threshold (40%). "
                    "Model rework required.",
                    timestamp=now,
                )
            )
        elif f1 < 0.6:
            alerts.append(
                Alert(
                    level="warning",
                    message=f"F1 score ({f1:.1%}) is below target threshold (60%). "
                    "Review model performance.",
                    timestamp=now,
                )
            )

        if len(trend) >= 3:
            recent_f1 = [t.f1_score for t in trend[-3:]]
            valid_f1 = [f for f in recent_f1 if f is not None and not math.isnan(f)]
            if len(valid_f1) >= 3:
                if all(valid_f1[i] > valid_f1[i + 1] for i in range(len(valid_f1) - 1)):
                    alerts.append(
                        Alert(
                            level="warning",
                            message="F1 score has declined for 3 consecutive measurements.",
                            timestamp=now,
                        )
                    )

        return alerts

    def _generate_alerts(
        self,
        latest: dict,
        trend: list[TrendDataPoint],
    ) -> list[Alert]:
        """Generate alerts based on metrics.

        Args:
            latest: Latest validation result
            trend: Historical trend data

        Returns:
            List of alerts
        """
        return self.generate_alerts(latest, trend, datetime.now())

    def save_metrics_to_history(
        self,
        conn: DuckDBConn,
        symbol: str,
        date: datetime,
        f1_score: float,
        precision: float,
        recall: float,
        run_id: str | None = None,
    ) -> None:
        """Save metrics to history table for trend tracking.

        Args:
            conn: DuckDB connection
            symbol: Trading pair
            date: Date of the metrics
            f1_score: F1 score
            precision: Precision
            recall: Recall
            run_id: Optional pipeline run ID
        """
        # Ensure table exists with composite primary key
        # Note: Using composite PK instead of separate id + unique index
        # to avoid DuckDB's "multiple unique constraints" conflict
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_metrics_history (
                date DATE NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                metric_type VARCHAR(20) NOT NULL,
                value DECIMAL(5,4) NOT NULL,
                source_run_id VARCHAR(36),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (date, symbol, metric_type)
            )
            """
        )

        # Insert or replace metrics
        metrics = [
            ("f1_score", f1_score),
            ("precision", precision),
            ("recall", recall),
        ]

        for metric_type, value in metrics:
            conn.execute(
                """
                INSERT OR REPLACE INTO validation_metrics_history
                (date, symbol, metric_type, value, source_run_id, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [date.date(), symbol, metric_type, value, run_id],
            )


def get_dashboard_metrics(
    symbol: str = "BTCUSDT",
    days: int = 30,
    db_path: str = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
) -> DashboardMetrics | None:
    """Convenience function to get dashboard metrics.

    Args:
        symbol: Trading pair
        days: Days of trend history
        db_path: Database path

    Returns:
        DashboardMetrics or None
    """
    aggregator = MetricsAggregator(db_path=db_path)
    return aggregator.get_dashboard_metrics(symbol=symbol, days=days)
