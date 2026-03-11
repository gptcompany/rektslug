"""Tests for scripts/ingest_oi.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.ingest_oi import main, get_oi_files, load_oi_streaming

class TestIngestOI:
    def test_get_oi_files_missing_dir(self, tmp_path):
        """Should raise FileNotFoundError if directory missing."""
        with pytest.raises(FileNotFoundError):
            get_oi_files(tmp_path, "BTCUSDT", "2024-01-01", "2024-01-01")

    def test_get_oi_files_success(self, tmp_path):
        """Should return existing files in range."""
        symbol = "BTCUSDT"
        metrics_dir = tmp_path / symbol / "metrics"
        metrics_dir.mkdir(parents=True)
        
        file1 = metrics_dir / f"{symbol}-metrics-2024-01-01.csv"
        file1.touch()
        file2 = metrics_dir / f"{symbol}-metrics-2024-01-02.csv"
        file2.touch()
        
        files = get_oi_files(tmp_path, symbol, "2024-01-01", "2024-01-03")
        assert len(files) == 2
        assert file1 in files
        assert file2 in files

    @patch("scripts.ingest_oi.get_oi_files")
    def test_load_oi_streaming_no_files(self, mock_get_files):
        """Should return 0 if no files found."""
        mock_get_files.return_value = []
        assert load_oi_streaming(MagicMock(), "/tmp", "BTCUSDT", "2024-01-01", "2024-01-01") == 0

    @patch("scripts.ingest_oi.get_oi_files")
    @patch("scripts.ingest_oi.time.sleep")
    def test_load_oi_streaming_success(self, mock_sleep, mock_get_files):
        """Should ingest files successfully."""
        mock_conn = MagicMock()
        file_path = Path("/tmp/BTCUSDT-metrics-2024-01-01.csv")
        mock_get_files.return_value = [file_path]
        
        # side_effects for conn.execute(...).fetchone()[0]
        mock_conn.execute.return_value.fetchone.side_effect = [
            (0,), # initial_count
            (100,), # csv_rows
            (0,), # max_id
            (100,), # current_count (after insert)
        ]
        
        total = load_oi_streaming(mock_conn, "/tmp", "BTCUSDT", "2024-01-01", "2024-01-01", throttle_ms=10)
        assert total == 100
        assert mock_sleep.called

    @patch("scripts.ingest_oi.duckdb.connect")
    @patch("scripts.ingest_oi.load_oi_streaming")
    def test_main_success(self, mock_load, mock_connect, monkeypatch):
        """Should run main successfully."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_load.return_value = 500
        
        mock_conn.execute.return_value.fetchone.side_effect = [
            (1000,), # count
            ("2024-01-01", "2024-01-03") # date range
        ]
        
        monkeypatch.setattr(sys, "argv", [
            "ingest_oi.py", 
            "--start-date", "2024-01-01", 
            "--end-date", "2024-01-03",
            "--data-dir", "/tmp/data"
        ])
        
        main()
        
        assert mock_load.called
        assert mock_conn.close.called
