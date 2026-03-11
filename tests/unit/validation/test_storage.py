"""Unit tests for validation storage."""

import os
from datetime import datetime, date
from unittest.mock import MagicMock, patch
import pytest
import duckdb
from src.validation.storage import ValidationStorage, StorageError
from src.models.validation_run import ValidationRun
from src.models.validation_test import ValidationTest
from src.models.validation_report import ValidationReport

class TestValidationStorage:
    def test_init(self):
        storage = ValidationStorage("test.db")
        assert storage.db_path == "test.db"
        assert storage.conn is None

    def test_connect_failure(self):
        with patch("src.validation.storage.duckdb.connect") as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            storage = ValidationStorage("test.db")
            with pytest.raises(StorageError, match="Failed to connect"):
                storage.connect()

    def test_init_schema(self, tmp_path):
        db_path = str(tmp_path / "test_schema.db")
        storage = ValidationStorage(db_path)
        with patch("src.validation.storage.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "CREATE TABLE test (id INT)"
            storage.init_schema()
            
        assert "test" in [t[0] for t in storage.conn.execute("SHOW TABLES").fetchall()]
        storage.close()

    def test_save_run(self, tmp_path):
        db_path = str(tmp_path / "test_save.db")
        storage = ValidationStorage(db_path)
        storage.connect()
        storage.conn.execute("""
            CREATE TABLE validation_runs (
                run_id VARCHAR PRIMARY KEY, model_name VARCHAR, trigger_type VARCHAR, triggered_by VARCHAR,
                started_at TIMESTAMP, completed_at TIMESTAMP, duration_seconds INTEGER,
                status VARCHAR, error_message VARCHAR, data_start_date DATE, data_end_date DATE,
                data_completeness DECIMAL, overall_grade VARCHAR, overall_score DECIMAL,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        
        mock_run = MagicMock(spec=ValidationRun)
        mock_run.run_id = "run1"
        mock_run.model_dump.return_value = {
            "run_id": "run1", "model_name": "m1", "trigger_type": "manual", "triggered_by": "u1",
            "started_at": datetime.now(), "completed_at": datetime.now(), "duration_seconds": 10,
            "status": "completed", "error_message": None, "data_start_date": date.today(),
            "data_end_date": date.today(), "data_completeness": 100.0, "overall_grade": "A",
            "overall_score": 95.0, "created_at": datetime.now(), "updated_at": datetime.now()
        }
        
        storage.save_run(mock_run)
        count = storage.conn.execute("SELECT COUNT(*) FROM validation_runs").fetchone()[0]
        assert count == 1
        storage.close()

    def test_save_test(self, tmp_path):
        db_path = str(tmp_path / "test_save_test.db")
        storage = ValidationStorage(db_path)
        storage.connect()
        storage.conn.execute("""
            CREATE TABLE validation_tests (
                test_id VARCHAR PRIMARY KEY, run_id VARCHAR, test_type VARCHAR, test_name VARCHAR,
                passed BOOLEAN, score DECIMAL, weight DECIMAL,
                primary_metric DECIMAL, secondary_metric DECIMAL,
                diagnostics JSON, error_message VARCHAR,
                executed_at TIMESTAMP, duration_ms INTEGER, created_at TIMESTAMP
            )
        """)
        
        mock_test = MagicMock(spec=ValidationTest)
        mock_test.test_id = "t1"
        mock_test.model_dump.return_value = {
            "test_id": "t1", "run_id": "run1", "test_type": "type1", "test_name": "name1",
            "passed": True, "score": 90.0, "weight": 0.5, "primary_metric": 0.9, "secondary_metric": 0.1,
            "diagnostics": '{"key": "val"}', "error_message": None, "executed_at": datetime.now(),
            "duration_ms": 100, "created_at": datetime.now()
        }
        
        storage.save_test(mock_test)
        count = storage.conn.execute("SELECT COUNT(*) FROM validation_tests").fetchone()[0]
        assert count == 1
        storage.close()

    def test_save_report(self, tmp_path):
        db_path = str(tmp_path / "test_save_report.db")
        storage = ValidationStorage(db_path)
        storage.connect()
        storage.conn.execute("""
            CREATE TABLE validation_reports (
                report_id VARCHAR PRIMARY KEY, run_id VARCHAR, format VARCHAR, report_content TEXT,
                summary JSON, recommendations JSON,
                alert_sent BOOLEAN, alert_sent_at TIMESTAMP, alert_recipients JSON,
                generated_at TIMESTAMP
            )
        """)
        
        mock_report = MagicMock(spec=ValidationReport)
        mock_report.report_id = "rep1"
        mock_report.model_dump.return_value = {
            "report_id": "rep1", "run_id": "run1", "format": "json", "report_content": "content",
            "summary": '{"s": 1}', "recommendations": '["r1"]', "alert_sent": False,
            "alert_sent_at": None, "alert_recipients": '[]', "generated_at": datetime.now()
        }
        
        storage.save_report(mock_report)
        count = storage.conn.execute("SELECT COUNT(*) FROM validation_reports").fetchone()[0]
        assert count == 1
        storage.close()

    def test_context_manager(self, tmp_path):
        db_path = str(tmp_path / "test_ctx.db")
        with ValidationStorage(db_path) as storage:
            assert storage.conn is not None
        assert storage.conn is None
