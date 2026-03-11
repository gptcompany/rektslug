"""Unit tests for validation data fetcher."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import pytest
from src.validation.data_fetcher import ValidationDataFetcher

class TestValidationDataFetcher:
    @patch("src.validation.data_fetcher.duckdb.connect")
    def test_connect_close(self, mock_connect):
        """Should connect and close database."""
        fetcher = ValidationDataFetcher(db_path=":memory:")
        fetcher.connect()
        assert mock_connect.called
        assert fetcher.conn is not None
        
        fetcher.close()
        assert fetcher.conn is None

    def test_get_data_window(self):
        """Should calculate correct start/end dates."""
        fetcher = ValidationDataFetcher()
        end_date = date(2024, 1, 31)
        start, end = fetcher.get_data_window(end_date=end_date, window_days=30)
        
        assert end == end_date
        assert start == end_date - timedelta(days=30)

    @patch("src.validation.data_fetcher.duckdb.connect")
    def test_fetch_methods_placeholder(self, mock_connect):
        """Should return empty lists (placeholders)."""
        fetcher = ValidationDataFetcher()
        start, end = date(2024, 1, 1), date(2024, 1, 31)
        
        assert fetcher.fetch_funding_rates(start, end) == []
        assert fetcher.fetch_open_interest(start, end) == []
        assert fetcher.fetch_liquidations(start, end) == []

    def test_check_data_completeness(self):
        """Should return 100.0 (placeholder)."""
        fetcher = ValidationDataFetcher()
        assert fetcher.check_data_completeness(date(2024, 1, 1), date(2024, 1, 2)) == 100.0

    @patch("src.validation.data_fetcher.duckdb.connect")
    def test_context_manager(self, mock_connect):
        """Should use context manager to connect/close."""
        with ValidationDataFetcher(db_path=":memory:") as fetcher:
            assert mock_connect.called
            assert fetcher.conn is not None
        assert fetcher.conn is None
