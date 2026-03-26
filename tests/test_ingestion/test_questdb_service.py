"""Tests for QuestDBService."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.liquidationheatmap.ingestion.questdb_service import QuestDBService


@pytest.fixture(autouse=True)
def reset_questdb_singleton():
    QuestDBService.reset_singleton()
    yield
    QuestDBService.reset_singleton()


def test_questdb_singleton():
    """QuestDBService should behave as a singleton."""
    with patch("src.liquidationheatmap.ingestion.questdb_service.Sender"):
        qdb1 = QuestDBService()
        qdb2 = QuestDBService()
    assert qdb1 is qdb2


def test_execute_query_handles_non_result_queries():
    """DDL queries should not fail when there is no result set to fetch."""
    with patch("src.liquidationheatmap.ingestion.questdb_service.Sender"):
        qdb = QuestDBService()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = None
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch.object(qdb, "_get_pg_conn", return_value=mock_conn):
        rows = qdb.execute_query("CREATE TABLE foo (id INT)")

    assert rows == []
    mock_conn.commit.assert_called_once()


def test_questdb_get_latest_open_interest():
    """Latest OI lookup should also fetch the latest QuestDB price."""
    with patch("src.liquidationheatmap.ingestion.questdb_service.Sender"):
        qdb = QuestDBService()

    qdb.execute_query = MagicMock(
        side_effect=[
            [(12345.6,)],
            [(50000.0,)],
        ]
    )

    price, oi = qdb.get_latest_open_interest("BTCUSDT")

    assert price == 50000.0
    assert oi == 12345.6
    assert qdb.execute_query.call_count == 2


def test_questdb_get_latest_funding_rate():
    """Funding rate lookup should return the latest float value."""
    with patch("src.liquidationheatmap.ingestion.questdb_service.Sender"):
        qdb = QuestDBService()

    qdb.execute_query = MagicMock(return_value=[(0.0001,)])

    rate = qdb.get_latest_funding_rate("BTCUSDT")

    assert rate == 0.0001
    qdb.execute_query.assert_called_once()


def test_get_recent_klines_serializes_timestamp():
    """Recent kline queries should expose API-ready keys and ISO timestamps."""
    with patch("src.liquidationheatmap.ingestion.questdb_service.Sender"):
        qdb = QuestDBService()

    ts = datetime(2026, 3, 26, 12, 0, tzinfo=timezone.utc)
    qdb.execute_query = MagicMock(return_value=[(ts, "BTCUSDT", "5m", 1.0, 2.0, 0.5, 1.5, 123.0)])

    rows = qdb.get_recent_klines("BTCUSDT", "5m", 10)

    assert rows == [
        {
            "open_time": ts.isoformat(),
            "symbol": "BTCUSDT",
            "interval": "5m",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 123.0,
        }
    ]


def test_get_open_interest_date_range_returns_none_without_data():
    """Date range helper should return None when QuestDB has no rows."""
    with patch("src.liquidationheatmap.ingestion.questdb_service.Sender"):
        qdb = QuestDBService()

    qdb.execute_query = MagicMock(return_value=[])

    assert qdb.get_open_interest_date_range("BTCUSDT") is None


def test_get_recent_liquidations_returns_api_ready_records():
    """Liquidation history helper should normalize QuestDB rows into dicts."""
    with patch("src.liquidationheatmap.ingestion.questdb_service.Sender"):
        qdb = QuestDBService()

    ts = datetime(2026, 3, 26, 12, 5, tzinfo=timezone.utc)
    qdb.execute_query = MagicMock(return_value=[(ts, "BTCUSDT", "long", 50000.0, 12.5, 25.0)])

    rows = qdb.get_recent_liquidations("BTCUSDT", 5)

    assert rows == [
        {
            "timestamp": ts.isoformat(),
            "symbol": "BTCUSDT",
            "side": "long",
            "price": 50000.0,
            "quantity": 12.5,
            "leverage": 25.0,
        }
    ]
