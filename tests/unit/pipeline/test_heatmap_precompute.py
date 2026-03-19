"""Tests for heatmap timeseries pre-computation script (spec-024 Phase 2)."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestPrecomputeSingle:
    """Test the incremental precompute logic."""

    def test_skips_when_cache_up_to_date(self, tmp_path):
        """When last cached timestamp is very recent, nothing to compute."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        with patch("src.liquidationheatmap.ingestion.db_service.DuckDBService") as MockDB:
            mock_ro = MagicMock()
            mock_ro.get_last_cached_ts_timestamp.return_value = now_str
            mock_ro.__enter__ = MagicMock(return_value=mock_ro)
            mock_ro.__exit__ = MagicMock(return_value=False)
            MockDB.return_value = mock_ro

            from scripts.precompute_heatmap_timeseries import precompute_single
            result = precompute_single("BTCUSDT", "15m", 30, 100.0)
            assert result == 0

    def test_computes_when_no_cache(self, tmp_path):
        """When cache is empty, computes from scratch."""
        mock_snapshot = MagicMock()
        mock_snapshot.to_dict.return_value = {
            "timestamp": "2026-03-19T12:00:00",
            "symbol": "BTCUSDT",
            "levels": [],
            "meta": {},
        }
        mock_snapshot.timestamp = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)

        with patch("src.liquidationheatmap.ingestion.db_service.DuckDBService") as MockDB:
            mock_ro = MagicMock()
            mock_ro.get_last_cached_ts_timestamp.return_value = None
            mock_ro.get_heatmap_timeseries.return_value = [mock_snapshot]
            mock_ro.__enter__ = MagicMock(return_value=mock_ro)
            mock_ro.__exit__ = MagicMock(return_value=False)

            mock_rw = MagicMock()
            mock_rw.put_cached_ts_snapshots.return_value = 1
            mock_rw.__enter__ = MagicMock(return_value=mock_rw)
            mock_rw.__exit__ = MagicMock(return_value=False)

            MockDB.side_effect = [mock_ro, mock_ro, mock_rw]

            from scripts.precompute_heatmap_timeseries import precompute_single
            result = precompute_single("BTCUSDT", "15m", 30, 100.0)
            assert result == 1
            mock_rw.put_cached_ts_snapshots.assert_called_once()


class TestCheckIngestionLock:
    def test_no_lock_file(self, tmp_path):
        from scripts.precompute_heatmap_timeseries import check_ingestion_lock
        with patch("scripts.precompute_heatmap_timeseries.INGESTION_LOCK_FILE", tmp_path / "nonexistent"):
            assert check_ingestion_lock() is False

    def test_fresh_lock_file(self, tmp_path):
        from scripts.precompute_heatmap_timeseries import check_ingestion_lock
        lock = tmp_path / "lock"
        lock.touch()
        with patch("scripts.precompute_heatmap_timeseries.INGESTION_LOCK_FILE", lock):
            assert check_ingestion_lock() is True


class TestDefaultConfigs:
    def test_configs_cover_btc_eth(self):
        from scripts.precompute_heatmap_timeseries import DEFAULT_CONFIGS
        symbols = {c["symbol"] for c in DEFAULT_CONFIGS}
        intervals = {c["interval"] for c in DEFAULT_CONFIGS}
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols
        assert "15m" in intervals
        assert "1h" in intervals
