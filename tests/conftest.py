"""Pytest configuration and shared fixtures."""

import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from src.liquidationheatmap.ingestion.db_service import DuckDBService


@pytest.fixture(autouse=True)
def reset_db_singletons():
    """Reset DuckDBService singletons and release locks before and after each test.

    This ensures test isolation - each test gets a fresh connection.
    Prevents 'different configuration' errors when mixing read-only/read-write.
    """
    # Reset before test
    DuckDBService.release_ingestion_lock()
    DuckDBService.reset_singletons()
    yield
    # Reset after test
    DuckDBService.release_ingestion_lock()
    DuckDBService.reset_singletons()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_db(temp_dir):
    """Create a temporary DuckDB database with schema."""
    db_path = temp_dir / "test_liquidations.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create test schema (simplified)
    conn.execute("""
        CREATE TABLE liquidation_levels (
            id BIGINT PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            model VARCHAR(50) NOT NULL,
            price_level DECIMAL(18, 2) NOT NULL,
            liquidation_volume DECIMAL(18, 8) NOT NULL,
            leverage_tier VARCHAR(10),
            side VARCHAR(10) NOT NULL,
            confidence DECIMAL(3, 2) NOT NULL
        );
    """)

    conn.execute("""
        CREATE TABLE open_interest_history (
            id BIGINT PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            open_interest_value DECIMAL(18, 8) NOT NULL
        );
    """)

    conn.execute("""
        CREATE TABLE funding_rate_history (
            id BIGINT PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            funding_rate DECIMAL(10, 8) NOT NULL
        );
    """)

    yield conn
    conn.close()


@pytest.fixture
def sample_csv_data():
    """Sample CSV data for testing ingestion."""
    return """timestamp,price,volume,side
1704067200000,42000.50,1.5,BUY
1704067260000,42010.25,0.8,SELL
1704067320000,42005.00,2.3,BUY
"""


@pytest.fixture
def sample_trade_data():
    """Sample trade data as list of dicts."""
    return [
        {"timestamp": 1704067200000, "price": 42000.50, "volume": 1.5, "side": "BUY"},
        {"timestamp": 1704067260000, "price": 42010.25, "volume": 0.8, "side": "SELL"},
        {"timestamp": 1704067320000, "price": 42005.00, "volume": 2.3, "side": "BUY"},
    ]


@pytest.fixture
def sample_open_interest_data():
    """Sample Open Interest data for testing liquidation calculations."""
    return [
        {
            "timestamp": datetime(2024, 10, 29, 12, 0, 0),
            "symbol": "BTCUSDT",
            "open_interest_value": Decimal("1234567890.12"),
        },
        {
            "timestamp": datetime(2024, 10, 29, 13, 0, 0),
            "symbol": "BTCUSDT",
            "open_interest_value": Decimal("1345678901.23"),
        },
    ]


@pytest.fixture
def sample_funding_rate_data():
    """Sample funding rate data for testing."""
    return [
        {
            "timestamp": datetime(2024, 10, 29, 0, 0, 0),
            "symbol": "BTCUSDT",
            "funding_rate": Decimal("0.0001"),
        },
        {
            "timestamp": datetime(2024, 10, 29, 8, 0, 0),
            "symbol": "BTCUSDT",
            "funding_rate": Decimal("0.0002"),
        },
    ]


@pytest.fixture
def sample_liquidation_levels():
    """Sample liquidation level data for testing."""
    return [
        {
            "id": 1,
            "timestamp": datetime(2024, 10, 29, 12, 0, 0),
            "symbol": "BTCUSDT",
            "model": "binance_standard",
            "price_level": Decimal("60000.00"),
            "liquidation_volume": Decimal("1234567.89"),
            "leverage_tier": "10x",
            "side": "long",
            "confidence": Decimal("0.95"),
        },
        {
            "id": 2,
            "timestamp": datetime(2024, 10, 29, 12, 0, 0),
            "symbol": "BTCUSDT",
            "model": "binance_standard",
            "price_level": Decimal("74000.00"),
            "liquidation_volume": Decimal("987654.32"),
            "leverage_tier": "10x",
            "side": "short",
            "confidence": Decimal("0.95"),
        },
    ]
