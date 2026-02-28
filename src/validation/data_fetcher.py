"""
Data fetcher for validation suite.

Fetches 30-day historical market data for validation tests.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import duckdb

from src.validation.constants import VALIDATION_WINDOW_DAYS


class ValidationDataFetcher:
    """
    Fetches historical market data for validation tests.

    Retrieves funding rates, open interest, and liquidation data
    from the past 30 days for validation analysis.
    """

    def __init__(self, db_path: str = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb"):
        """
        Initialize data fetcher.

        Args:
            db_path: Path to DuckDB database
        """
        self.db_path = db_path
        self.conn: Optional[duckdb.DuckDBPyConnection] = None

    def connect(self):
        """Establish database connection."""
        if self.conn is None:
            self.conn = duckdb.connect(self.db_path, read_only=True)

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_data_window(
        self, end_date: Optional[date] = None, window_days: int = VALIDATION_WINDOW_DAYS
    ) -> tuple[date, date]:
        """
        Calculate validation data window.

        Args:
            end_date: End date (defaults to today)
            window_days: Number of days to look back

        Returns:
            Tuple of (start_date, end_date)
        """
        if end_date is None:
            end_date = datetime.utcnow().date()

        start_date = end_date - timedelta(days=window_days)
        return start_date, end_date

    def fetch_funding_rates(
        self, start_date: date, end_date: date, symbol: str = "BTCUSDT"
    ) -> list[dict]:
        """
        Fetch funding rate data for validation.

        Args:
            start_date: Start of data window
            end_date: End of data window
            symbol: Trading pair symbol

        Returns:
            List of funding rate records
        """
        self.connect()

        # Placeholder: actual implementation would query funding_rates table
        # For now, return empty list until ingestion is complete
        return []

    def fetch_open_interest(
        self, start_date: date, end_date: date, symbol: str = "BTCUSDT"
    ) -> list[dict]:
        """
        Fetch open interest data for validation.

        Args:
            start_date: Start of data window
            end_date: End of data window
            symbol: Trading pair symbol

        Returns:
            List of OI records
        """
        self.connect()

        # Placeholder: actual implementation would query oi_data table
        return []

    def fetch_liquidations(
        self, start_date: date, end_date: date, symbol: str = "BTCUSDT"
    ) -> list[dict]:
        """
        Fetch historical liquidation data.

        Args:
            start_date: Start of data window
            end_date: End of data window
            symbol: Trading pair symbol

        Returns:
            List of liquidation records
        """
        self.connect()

        # Placeholder: actual implementation would query liquidations table
        return []

    def check_data_completeness(self, start_date: date, end_date: date) -> Decimal:
        """
        Check data completeness percentage.

        Args:
            start_date: Start of window
            end_date: End of window

        Returns:
            Completeness percentage (0-100)
        """
        # Placeholder: calculate expected vs actual data points
        # For now, assume 100% completeness
        return Decimal("100.0")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
