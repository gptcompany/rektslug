"""Integration tests for feedback storage.

Tests FeedbackConsumer with real DuckDB (in-memory).
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pytest

from src.liquidationheatmap.signals.models import TradeFeedback


class TestFeedbackStorage:
    """Integration tests for feedback DuckDB storage."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary DuckDB database."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_feedback.duckdb"
            conn = duckdb.connect(str(db_path))

            # Run migration
            migration_sql = Path("scripts/migrations/add_signal_feedback_table.sql").read_text()
            conn.execute(migration_sql)

            yield conn
            conn.close()

    def test_store_feedback_inserts_row(self, temp_db):
        """store_feedback should insert a row into DuckDB."""
        from src.liquidationheatmap.signals.feedback import FeedbackDBService

        db_service = FeedbackDBService(temp_db)

        feedback = TradeFeedback(
            symbol="BTCUSDT",
            signal_id="abc123",
            entry_price=Decimal("95000.00"),
            exit_price=Decimal("95500.00"),
            pnl=Decimal("500.00"),
            timestamp=datetime(2025, 12, 28, 11, 0, 0),
            source="nautilus",
        )

        result = db_service.store_feedback(feedback)
        assert result is True

        # Verify row was inserted
        rows = temp_db.execute(
            "SELECT * FROM signal_feedback WHERE signal_id = 'abc123'"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row[1] == "BTCUSDT"  # symbol
        assert row[2] == "abc123"  # signal_id

    def test_store_multiple_feedback(self, temp_db):
        """Should store multiple feedback records."""
        from src.liquidationheatmap.signals.feedback import FeedbackDBService

        db_service = FeedbackDBService(temp_db)

        for i in range(5):
            feedback = TradeFeedback(
                symbol="BTCUSDT",
                signal_id=f"signal_{i}",
                entry_price=Decimal("95000"),
                exit_price=Decimal("95500"),
                pnl=Decimal("500"),
                timestamp=datetime(2025, 12, 28, 11, i, 0),
                source="nautilus",
            )
            db_service.store_feedback(feedback)

        count = temp_db.execute("SELECT COUNT(*) FROM signal_feedback").fetchone()[0]
        assert count == 5

    def test_query_rolling_metrics(self, temp_db):
        """Should support rolling metric queries."""
        from datetime import timedelta, timezone

        from src.liquidationheatmap.signals.feedback import FeedbackDBService

        db_service = FeedbackDBService(temp_db)

        # Insert mix of profitable and unprofitable feedback
        # Use timestamps relative to now so they fall within the 24h window
        now = datetime.now(timezone.utc)
        for i in range(10):
            pnl = Decimal("100") if i % 2 == 0 else Decimal("-50")
            feedback = TradeFeedback(
                symbol="BTCUSDT",
                signal_id=f"signal_{i}",
                entry_price=Decimal("95000"),
                exit_price=Decimal("95100") if i % 2 == 0 else Decimal("94950"),
                pnl=pnl,
                timestamp=now - timedelta(hours=i),  # Recent timestamps within 24h window
                source="nautilus",
            )
            db_service.store_feedback(feedback)

        # Query metrics
        metrics = db_service.get_rolling_metrics("BTCUSDT", hours=24)

        assert metrics["total"] == 10
        assert metrics["profitable"] == 5
        assert metrics["hit_rate"] == 0.5


class TestFeedbackDBService:
    """Unit tests for FeedbackDBService."""

    @pytest.fixture
    def in_memory_db(self):
        """Create in-memory DuckDB."""
        conn = duckdb.connect(":memory:")

        # Run migration
        migration_sql = Path("scripts/migrations/add_signal_feedback_table.sql").read_text()
        conn.execute(migration_sql)

        yield conn
        conn.close()

    def test_store_feedback_with_negative_pnl(self, in_memory_db):
        """Should store feedback with negative P&L."""
        from src.liquidationheatmap.signals.feedback import FeedbackDBService

        db_service = FeedbackDBService(in_memory_db)

        feedback = TradeFeedback(
            symbol="BTCUSDT",
            signal_id="loss_trade",
            entry_price=Decimal("95000"),
            exit_price=Decimal("94000"),
            pnl=Decimal("-1000"),
            source="nautilus",
        )

        result = db_service.store_feedback(feedback)
        assert result is True

        row = in_memory_db.execute(
            "SELECT pnl FROM signal_feedback WHERE signal_id = 'loss_trade'"
        ).fetchone()
        assert row[0] < 0

    def test_get_feedback_by_symbol(self, in_memory_db):
        """Should query feedback by symbol."""
        from src.liquidationheatmap.signals.feedback import FeedbackDBService

        db_service = FeedbackDBService(in_memory_db)

        # Insert for different symbols
        for symbol in ["BTCUSDT", "ETHUSDT", "BTCUSDT"]:
            feedback = TradeFeedback(
                symbol=symbol,
                signal_id=f"{symbol}_001",
                entry_price=Decimal("1000"),
                exit_price=Decimal("1100"),
                pnl=Decimal("100"),
                source="nautilus",
            )
            db_service.store_feedback(feedback)

        btc_count = in_memory_db.execute(
            "SELECT COUNT(*) FROM signal_feedback WHERE symbol = 'BTCUSDT'"
        ).fetchone()[0]

        assert btc_count == 2

    def test_get_rolling_metrics_handles_missing_table(self):
        """get_rolling_metrics should return empty metrics if table doesn't exist.

        Edge case: When the database is new and migrations haven't run yet,
        the function should gracefully return empty metrics instead of crashing.
        """
        from src.liquidationheatmap.signals.feedback import FeedbackDBService

        # Create a fresh in-memory DB without running migrations
        conn = duckdb.connect(":memory:")
        db_service = FeedbackDBService(conn)

        # Should return empty metrics, not crash
        metrics = db_service.get_rolling_metrics("BTCUSDT", hours=24)

        assert metrics["total"] == 0
        assert metrics["profitable"] == 0
        assert metrics["unprofitable"] == 0
        assert metrics["hit_rate"] == 0.0
        assert metrics["avg_pnl"] == 0.0

        conn.close()

    def test_store_feedback_bootstraps_schema_from_heatmap_db_path(self, monkeypatch):
        """Runtime storage should create the feedback schema on first write."""
        from src.liquidationheatmap.signals.feedback import FeedbackDBService

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime_feedback.duckdb"
            monkeypatch.delenv("FEEDBACK_DB_PATH", raising=False)
            monkeypatch.setenv("HEATMAP_DB_PATH", str(db_path))

            db_service = FeedbackDBService()
            feedback = TradeFeedback(
                symbol="ETHUSDT",
                signal_id="bootstrap_001",
                entry_price=Decimal("1800"),
                exit_price=Decimal("1810"),
                pnl=Decimal("10"),
                source="nautilus",
            )

            assert db_service.store_feedback(feedback) is True
            db_service.close()

            conn = duckdb.connect(str(db_path), read_only=True)
            try:
                row = conn.execute(
                    "SELECT symbol, signal_id FROM signal_feedback WHERE signal_id = 'bootstrap_001'"
                ).fetchone()
            finally:
                conn.close()

            assert row == ("ETHUSDT", "bootstrap_001")
