"""Tests for scripts/ingest_klines_15m.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import duckdb
from scripts.ingest_klines_15m import main, get_klines_files, load_klines_streaming, create_klines_table

class TestIngestKlines:
    def test_get_klines_files_missing_dir(self, tmp_path):
        """Should raise FileNotFoundError if directory missing."""
        with pytest.raises(FileNotFoundError):
            get_klines_files(tmp_path, "BTCUSDT", "2024-01-01", "2024-01-01")

    def test_get_klines_files_success(self, tmp_path):
        """Should return existing files in range."""
        symbol = "BTCUSDT"
        interval = "15m"
        klines_dir = tmp_path / symbol / "klines" / interval
        klines_dir.mkdir(parents=True)
        
        file1 = klines_dir / f"{symbol}-{interval}-2024-01-01.csv"
        file1.touch()
        
        files = get_klines_files(tmp_path, symbol, "2024-01-01", "2024-01-01", interval)
        assert len(files) == 1
        assert file1 in files

    def test_create_klines_table(self):
        """Should execute CREATE TABLE statement."""
        mock_conn = MagicMock()
        create_klines_table(mock_conn, "15m")
        assert mock_conn.execute.called
        assert "CREATE TABLE IF NOT EXISTS klines_15m_history" in mock_conn.execute.call_args[0][0]

    @patch("scripts.ingest_klines_15m.get_klines_files")
    def test_load_klines_streaming_no_files(self, mock_get_files):
        """Should return 0 if no files found."""
        mock_get_files.return_value = []
        assert load_klines_streaming(MagicMock(), "/tmp", "BTCUSDT", "2024-01-01", "2024-01-01") == 0

    @patch("scripts.ingest_klines_15m.get_klines_files")
    @patch("scripts.ingest_klines_15m.time.sleep")
    def test_load_klines_streaming_success_header(self, mock_sleep, mock_get_files):
        """Should ingest files successfully with header format."""
        mock_conn = MagicMock()
        file_path = Path("/tmp/BTCUSDT-15m-2024-01-01.csv")
        mock_get_files.return_value = [file_path]
        
        # mock returns for execute().fetchone()
        res = MagicMock()
        res.fetchone.side_effect = [(0,), (100,), (100,)]
        mock_conn.execute.return_value = res
        
        total = load_klines_streaming(mock_conn, "/tmp", "BTCUSDT", "2024-01-01", "2024-01-01", throttle_ms=10)
        assert total == 100
        assert mock_sleep.called

    @patch("scripts.ingest_klines_15m.get_klines_files")
    @patch("scripts.ingest_klines_15m.time.sleep")
    def test_load_klines_streaming_fallback_no_header(self, mock_sleep, mock_get_files):
        """Should fallback to no-header format if BinderException occurs."""
        mock_conn = MagicMock()
        file_path = Path("/tmp/BTCUSDT-15m-2024-01-01.csv")
        mock_get_files.return_value = [file_path]
        
        # 1. create_klines_table -> execute (returns None usually)
        # 2. initial_count -> execute().fetchone() -> (0,)
        # 3. csv_rows (header=true) -> execute() -> raises BinderException
        # 4. csv_rows (header=false) -> execute().fetchone() -> (100,)
        # 5. INSERT (header=false) -> execute() -> None
        # 6. current_count -> execute().fetchone() -> (100,)
        
        res_initial = MagicMock()
        res_initial.fetchone.return_value = (0,)
        
        res_csv_no_header = MagicMock()
        res_csv_no_header.fetchone.return_value = (100,)
        
        res_current = MagicMock()
        res_current.fetchone.return_value = (100,)
        
        mock_conn.execute.side_effect = [
            None, # create_klines_table
            res_initial, # initial_count
            duckdb.BinderException("column open_time not found"), # header=true fails
            res_csv_no_header, # csv_rows (header=false)
            None, # INSERT (header=false)
            res_current, # current_count
        ]
        
        total = load_klines_streaming(mock_conn, "/tmp", "BTCUSDT", "2024-01-01", "2024-01-01", throttle_ms=10)
        assert total == 100

    @patch("scripts.ingest_klines_15m.duckdb.connect")
    @patch("scripts.ingest_klines_15m.load_klines_streaming")
    def test_main_success(self, mock_load, mock_connect, monkeypatch):
        """Should run main successfully."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_load.return_value = 500
        
        res1 = MagicMock()
        res1.fetchone.return_value = (1000,)
        res2 = MagicMock()
        res2.fetchone.return_value = ("2024-01-01", "2024-01-03")
        
        mock_conn.execute.side_effect = [res1, res2]
        
        monkeypatch.setattr(sys, "argv", [
            "ingest_klines_15m.py", 
            "--start-date", "2024-01-01", 
            "--end-date", "2024-01-03",
            "--data-dir", "/tmp/data"
        ])
        
        main()
        
        assert mock_load.called
        assert mock_connect.called
        assert mock_conn.close.called
