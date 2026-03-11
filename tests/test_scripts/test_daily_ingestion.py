"""Tests for scripts/daily_ingestion.py."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from scripts.daily_ingestion import main, run_script

class TestDailyIngestion:
    @patch("scripts.daily_ingestion.subprocess.run")
    def test_run_script_success(self, mock_run):
        """Should return True if script succeeds."""
        mock_run.return_value = MagicMock(returncode=0)
        
        assert run_script("test.py", ["--arg", "val"]) is True
        assert mock_run.called

    @patch("scripts.daily_ingestion.subprocess.run")
    def test_run_script_failure(self, mock_run):
        """Should return False if script fails."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Error")
        
        assert run_script("test.py", []) is False

    @patch("scripts.daily_ingestion.subprocess.run")
    def test_run_script_timeout(self, mock_run):
        """Should return False if script times out."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["test"], timeout=600)
        
        assert run_script("test.py", []) is False

    @patch("scripts.daily_ingestion.sys.exit")
    @patch("scripts.daily_ingestion.run_script", return_value=True)
    def test_main_success(self, mock_run_script, mock_exit, monkeypatch):
        """Main should exit with 0 if all scripts succeed."""
        monkeypatch.setattr(sys, "argv", ["daily_ingestion.py", "--symbol", "BTCUSDT"])
        main()
        mock_exit.assert_called_once_with(0)
        # 3 calls: 5m klines, 15m klines, OI
        assert mock_run_script.call_count == 3

    @patch("scripts.daily_ingestion.sys.exit")
    @patch("scripts.daily_ingestion.run_script", side_effect=[True, False, True])
    def test_main_partial_failure(self, mock_run_script, mock_exit, monkeypatch):
        """Main should exit with 1 if any script fails."""
        monkeypatch.setattr(sys, "argv", ["daily_ingestion.py", "--symbol", "BTCUSDT"])
        main()
        mock_exit.assert_called_once_with(1)

    @patch("scripts.daily_ingestion.sys.exit")
    @patch("scripts.daily_ingestion.run_script", return_value=True)
    def test_main_klines_only(self, mock_run_script, mock_exit, monkeypatch):
        """Main should skip OI if --klines-only is provided."""
        monkeypatch.setattr(sys, "argv", ["daily_ingestion.py", "--symbol", "BTCUSDT", "--klines-only"])
        main()
        mock_exit.assert_called_once_with(0)
        # 2 calls: 5m klines, 15m klines
        assert mock_run_script.call_count == 2
