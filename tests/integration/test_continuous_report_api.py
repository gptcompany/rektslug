from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import duckdb
import pytest
from fastapi.testclient import TestClient

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.signals.feedback import FeedbackDBService
from src.liquidationheatmap.signals.models import TradeFeedback

@pytest.fixture
def temp_db_path():
    """Create a temporary DuckDB database path."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_feedback.duckdb"
        
        # Initialize schema
        conn = duckdb.connect(str(db_path))
        migration_sql = Path("scripts/migrations/add_signal_feedback_table.sql").read_text()
        conn.execute(migration_sql)
        conn.close()
        
        yield str(db_path)

def test_continuous_report_returns_measured_values(temp_db_path, monkeypatch):
    """
    T013R RED: assert continuous metrics return measured values from actual runtime counters.
    T014 Ensure feedback_persisted is counted from actual DuckDB writes.
    """
    monkeypatch.setenv("FEEDBACK_DB_PATH", temp_db_path)
    
    # Initialize DB and insert feedback via the DB service
    db_service = FeedbackDBService()
    feedback = TradeFeedback(
        symbol="BTCUSDT",
        signal_id="continuous_1",
        entry_price=Decimal("95000"),
        exit_price=Decimal("95500"),
        pnl=Decimal("500"),
        source="nautilus"
    )
    db_service.store_feedback(feedback)
    db_service.close()
    
    client = TestClient(app)
    response = client.get("/signals/continuous-report")
    
    assert response.status_code == 200
    data = response.json()
    
    # Must use the machine-readable contract
    assert "feedback_persisted" in data
    assert "signals_seen" in data
    assert "orders_submitted" in data
    
    # Must return measured value (1 write)
    assert data["feedback_persisted"] == 1
