"""Tests for scripts/check_ingestion_ready.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.check_ingestion_ready import (
    check_lock_available,
    check_disk_space,
    check_database_connectivity,
    check_csv_samples,
    main
)

class TestCheckIngestionReady:
    @patch("scripts.check_ingestion_ready.fcntl.flock")
    @patch("scripts.check_ingestion_ready.open")
    def test_check_lock_available_success(self, mock_open, mock_flock):
        """Should return True when lock is available."""
        mock_file = MagicMock()
        mock_open.return_value = mock_file
        
        assert check_lock_available() is True
        assert mock_open.called
        assert mock_flock.called

    @patch("scripts.check_ingestion_ready.fcntl.flock")
    @patch("scripts.check_ingestion_ready.open")
    def test_check_lock_available_failure(self, mock_open, mock_flock):
        """Should return False when lock is held."""
        mock_open.return_value = MagicMock()
        mock_flock.side_effect = BlockingIOError()
        
        assert check_lock_available() is False

    @patch("scripts.check_ingestion_ready.shutil.disk_usage")
    def test_check_disk_space_success(self, mock_disk_usage):
        """Should return True when enough disk space."""
        # 200 GB free
        mock_disk_usage.return_value = MagicMock(free=200 * 1024**3, total=1000 * 1024**3, used=800 * 1024**3)
        
        assert check_disk_space("/some/db.duckdb") is True

    @patch("scripts.check_ingestion_ready.shutil.disk_usage")
    def test_check_disk_space_failure(self, mock_disk_usage):
        """Should return False when not enough disk space."""
        # 10 GB free
        mock_disk_usage.return_value = MagicMock(free=10 * 1024**3, total=1000 * 1024**3, used=990 * 1024**3)
        
        assert check_disk_space("/some/db.duckdb") is False

    @patch("scripts.check_ingestion_ready.duckdb.connect")
    def test_check_database_connectivity_success(self, mock_connect):
        """Should return True when database is accessible."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = (100,)
        
        assert check_database_connectivity("/some/db.duckdb") is True

    @patch("scripts.check_ingestion_ready.duckdb.connect")
    def test_check_database_connectivity_failure(self, mock_connect):
        """Should return False when database connection fails."""
        mock_connect.side_effect = Exception("Connection error")
        
        assert check_database_connectivity("/some/db.duckdb") is False

    def test_check_csv_samples_missing_dir(self, tmp_path):
        """Should return False if data directory does not exist."""
        assert check_csv_samples(tmp_path / "nonexistent") is False

    def test_check_csv_samples_success(self, tmp_path):
        """Should return True if CSV files are valid."""
        symbol = "BTCUSDT"
        aggtrades_dir = tmp_path / symbol / "aggTrades"
        aggtrades_dir.mkdir(parents=True)
        
        # Create some valid CSV files
        for i in range(3):
            csv_file = aggtrades_dir / f"trades_{i}.csv"
            csv_file.write_text("timestamp,price,volume,side\n1704067200000,42000.50,1.5,BUY")
            
        assert check_csv_samples(tmp_path, symbol=symbol) is True

    def test_check_csv_samples_corrupted(self, tmp_path):
        """Should return False if CSV files are empty."""
        symbol = "BTCUSDT"
        aggtrades_dir = tmp_path / symbol / "aggTrades"
        aggtrades_dir.mkdir(parents=True)
        
        csv_file = aggtrades_dir / "corrupted.csv"
        csv_file.write_text("")  # Empty
            
        assert check_csv_samples(tmp_path, symbol=symbol) is False

    @patch("scripts.check_ingestion_ready.sys.exit")
    @patch("scripts.check_ingestion_ready.check_lock_available", return_value=True)
    @patch("scripts.check_ingestion_ready.check_disk_space", return_value=True)
    @patch("scripts.check_ingestion_ready.check_database_connectivity", return_value=True)
    @patch("scripts.check_ingestion_ready.check_csv_samples", return_value=True)
    def test_main_success(self, mock_csv, mock_db, mock_disk, mock_lock, mock_exit, monkeypatch):
        """Main should exit with 0 when all checks pass."""
        monkeypatch.setattr(sys, "argv", ["check_ingestion_ready.py", "--db", "db", "--data-dir", "data"])
        
        main()
        mock_exit.assert_called_once_with(0)

    @patch("scripts.check_ingestion_ready.sys.exit")
    @patch("scripts.check_ingestion_ready.check_lock_available", return_value=False)
    @patch("scripts.check_ingestion_ready.check_disk_space", return_value=True)
    @patch("scripts.check_ingestion_ready.check_database_connectivity", return_value=True)
    @patch("scripts.check_ingestion_ready.check_csv_samples", return_value=True)
    def test_main_failure(self, mock_csv, mock_db, mock_disk, mock_lock, mock_exit, monkeypatch):
        """Main should exit with 1 when some checks fail."""
        monkeypatch.setattr(sys, "argv", ["check_ingestion_ready.py", "--db", "db", "--data-dir", "data"])
        
        main()
        mock_exit.assert_called_once_with(1)
