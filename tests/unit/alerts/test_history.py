"""Unit tests for alert history store."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
import pytest
from src.liquidationheatmap.alerts.history import AlertHistoryStore
from src.liquidationheatmap.alerts.models import Alert, AlertSeverity, DeliveryStatus

class TestAlertHistoryStore:
    def test_init_and_schema(self, tmp_path):
        db_path = tmp_path / "alerts.duckdb"
        store = AlertHistoryStore(db_path)
        
        # Verify table exists
        conn = store._get_connection()
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "alert_history" in table_names
        conn.close()

    def test_save_and_get_recent(self, tmp_path):
        db_path = tmp_path / "alerts.duckdb"
        store = AlertHistoryStore(db_path)
        
        alert = Alert(
            symbol="BTCUSDT",
            current_price=Decimal("70000"),
            zone_price=Decimal("65000"),
            zone_density=Decimal("1000000"),
            zone_side="long",
            distance_pct=Decimal("7.14"),
            severity=AlertSeverity.WARNING,
            message="Test alert",
            channels_sent=["telegram", "discord"],
            delivery_status=DeliveryStatus.SUCCESS
        )
        
        alert_id = store.save_alert(alert)
        assert alert_id == 1
        
        recent = store.get_recent_alerts(limit=10)
        assert len(recent) == 1
        saved = recent[0]
        assert saved.symbol == "BTCUSDT"
        assert saved.severity == AlertSeverity.WARNING
        assert saved.channels_sent == ["telegram", "discord"]
        assert saved.delivery_status == DeliveryStatus.SUCCESS

    def test_cleanup_old_alerts(self, tmp_path):
        db_path = tmp_path / "alerts.duckdb"
        store = AlertHistoryStore(db_path, retention_days=7)
        
        # Save one old and one new alert
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=10)
        
        alert_old = Alert(
            timestamp=old_time,
            symbol="BTCUSDT",
            current_price=Decimal("70000"),
            zone_price=Decimal("60000"),
            zone_density=Decimal("100"),
            zone_side="long",
            distance_pct=Decimal("14"),
            severity=AlertSeverity.INFO,
            message="Old alert"
        )
        alert_new = Alert(
            timestamp=now,
            symbol="BTCUSDT",
            current_price=Decimal("70000"),
            zone_price=Decimal("60000"),
            zone_density=Decimal("100"),
            zone_side="long",
            distance_pct=Decimal("14"),
            severity=AlertSeverity.INFO,
            message="New alert"
        )
        
        store.save_alert(alert_old)
        store.save_alert(alert_new)
        
        assert store.get_alert_count() == 2
        
        deleted = store.cleanup_old_alerts()
        assert deleted == 1
        assert store.get_alert_count() == 1

    def test_get_alert_count_with_since(self, tmp_path):
        db_path = tmp_path / "alerts.duckdb"
        store = AlertHistoryStore(db_path)
        
        now = datetime.now(timezone.utc)
        alert = Alert(timestamp=now, symbol="BTCUSDT", current_price=Decimal("70000"), zone_price=Decimal("60000"), zone_density=Decimal("100"), zone_side="long", distance_pct=Decimal("14"), message="Test")
        store.save_alert(alert)
        
        assert store.get_alert_count(since=now - timedelta(hours=1)) == 1
        assert store.get_alert_count(since=now + timedelta(hours=1)) == 0
