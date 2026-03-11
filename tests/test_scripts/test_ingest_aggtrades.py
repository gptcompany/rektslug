"""Tests for scripts/ingest_aggtrades.py."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from scripts.ingest_aggtrades import main

class TestIngestAggtrades:
    @patch("scripts.ingest_aggtrades.duckdb.connect")
    @patch("scripts.ingest_aggtrades.load_aggtrades_streaming")
    def test_main_success(self, mock_load, mock_connect, monkeypatch):
        """Should run ingestion successfully."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_load.return_value = 1000
        
        mock_conn.execute.return_value.fetchone.side_effect = [
            (5000,), # count
            ("2024-01-01", "2024-01-03") # date range
        ]
        
        monkeypatch.setattr(sys, "argv", [
            "ingest_aggtrades.py", 
            "--start-date", "2024-01-01", 
            "--end-date", "2024-01-03",
            "--data-dir", "/tmp/data"
        ])
        
        main()
        
        assert mock_load.called
        assert mock_connect.called
        assert mock_conn.close.called

    @patch("scripts.ingest_aggtrades.duckdb.connect")
    @patch("scripts.ingest_aggtrades.load_aggtrades_streaming")
    def test_main_error(self, mock_load, mock_connect, monkeypatch):
        """Should raise error if ingestion fails."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_load.side_effect = Exception("Ingestion failed")
        
        monkeypatch.setattr(sys, "argv", [
            "ingest_aggtrades.py", 
            "--start-date", "2024-01-01", 
            "--end-date", "2024-01-03",
            "--data-dir", "/tmp/data"
        ])
        
        with pytest.raises(Exception, match="Ingestion failed"):
            main()
        
        assert mock_conn.close.called
