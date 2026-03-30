"""Unit tests for gap_fill.py edge cases."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pandas as pd
import pytest

from src.liquidationheatmap.ingestion.gap_fill import (
    _kline_minutes,
    _fill_klines_interval,
    fill_open_interest,
    fill_funding_rate,
    validate_gaps,
    run_gap_fill
)

@pytest.fixture
def mock_questdb():
    """Mock QuestDBService for unit tests."""
    mock = MagicMock()
    mock._sender = object()
    return mock

def test_kline_minutes_invalid():
    """Test _kline_minutes raises ValueError for invalid input."""
    with pytest.raises(ValueError, match="Unsupported kline interval"):
        _kline_minutes("1h")
    with pytest.raises(ValueError, match="Unsupported kline interval"):
        _kline_minutes("m")
    with pytest.raises(ValueError, match="Unsupported kline interval"):
        _kline_minutes("5")

def test_fill_klines_no_table(tmp_path, mock_questdb):
    """Test _fill_klines_interval handles missing table gracefully."""
    con = MagicMock()
    # Mock QuestDB watermark
    with patch("src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark", return_value=None), \
         patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        
        con.execute.side_effect = Exception("No files")
        
        result = _fill_klines_interval(con, mock_questdb, str(tmp_path), "BTCUSDT", "1m", False)
        
        assert result["inserted"] == 0
        assert result["skipped"] == "no_parquet"

def test_fill_klines_no_parquet(tmp_path, mock_questdb):
    """Test _fill_klines_interval handles Exception when counting Parquet."""
    con = MagicMock()
    with patch("src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark", return_value=datetime(2025, 1, 1)), \
         patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        
        con.execute.side_effect = Exception("File not found")
        result = _fill_klines_interval(con, mock_questdb, str(tmp_path), "BTCUSDT", "5m", False)
        assert result["skipped"] == "no_parquet"

def test_fill_klines_dry_run(tmp_path, mock_questdb):
    """Test _fill_klines_interval dry_run mode."""
    con = MagicMock()
    with patch("src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark", return_value=datetime(2025, 1, 1)), \
         patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        
        con.execute.return_value.fetchone.return_value = [10]
        result = _fill_klines_interval(con, mock_questdb, str(tmp_path), "BTCUSDT", "5m", True)
        assert result["skipped"] == "dry_run"
        assert result["available"] == 10

def test_fill_klines_localizes_dataframe_timestamps_to_utc(tmp_path, mock_questdb):
    """QuestDB ingest should receive UTC-aware timestamps from gap fill."""
    con = MagicMock()
    count_result = MagicMock()
    count_result.fetchone.return_value = [1]
    dataframe_result = MagicMock()
    dataframe_result.df.return_value = pd.DataFrame(
        {
            "timestamp": [datetime(2025, 1, 1, 0, 5)],
            "symbol": ["BTCUSDT"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [42.0],
        }
    )
    con.execute.side_effect = [count_result, dataframe_result]

    with patch(
        "src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark",
        return_value=datetime(2025, 1, 1),
    ), patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        result = _fill_klines_interval(con, mock_questdb, str(tmp_path), "BTCUSDT", "5m", False)

    assert result["inserted"] == 1
    ingest_args = mock_questdb.ingest_dataframe.call_args[0]
    ingested_df = ingest_args[1]
    assert str(ingested_df["timestamp"].dtype) == "datetime64[ns, UTC]"
    assert str(ingested_df["timestamp"].dt.tz) == "UTC"

def test_fill_open_interest_bootstrap(tmp_path, mock_questdb):
    """Test fill_open_interest bootstraps when watermark is None."""
    con = MagicMock()
    with patch("src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark", return_value=None), \
         patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        
        con.execute.return_value.fetchone.return_value = [0]
        result = fill_open_interest(con, mock_questdb, str(tmp_path), "BTCUSDT", False)
        assert result["skipped"] == "up_to_date"

def test_fill_open_interest_no_parquet(tmp_path, mock_questdb):
    """Test fill_open_interest handles Exception when counting Parquet."""
    con = MagicMock()
    with patch("src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark", return_value=datetime(2025, 1, 1)), \
         patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        
        con.execute.side_effect = Exception("File not found")
        result = fill_open_interest(con, mock_questdb, str(tmp_path), "BTCUSDT", False)
        assert result["skipped"] == "no_parquet"

def test_fill_open_interest_dry_run(tmp_path, mock_questdb):
    """Test fill_open_interest dry_run mode."""
    con = MagicMock()
    with patch("src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark", return_value=datetime(2025, 1, 1)), \
         patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        
        con.execute.return_value.fetchone.return_value = [20]
        result = fill_open_interest(con, mock_questdb, str(tmp_path), "BTCUSDT", True)
        assert result["skipped"] == "dry_run"
        assert result["available"] == 20

def test_fill_funding_bootstrap(tmp_path, mock_questdb):
    """Test fill_funding_rate bootstraps when watermark is None."""
    con = MagicMock()
    with patch("src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark", return_value=None), \
         patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        
        con.execute.return_value.fetchone.return_value = [0]
        result = fill_funding_rate(con, mock_questdb, str(tmp_path), "BTCUSDT", False)
        assert result["skipped"] == "up_to_date"

def test_fill_funding_no_parquet(tmp_path, mock_questdb):
    """Test fill_funding_rate handles Exception when counting Parquet."""
    con = MagicMock()
    with patch("src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark", return_value=datetime(2025, 1, 1)), \
         patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        
        con.execute.side_effect = Exception("File not found")
        result = fill_funding_rate(con, mock_questdb, str(tmp_path), "BTCUSDT", False)
        assert result["skipped"] == "no_parquet"

def test_fill_funding_dry_run(tmp_path, mock_questdb):
    """Test fill_funding_rate dry_run mode."""
    con = MagicMock()
    with patch("src.liquidationheatmap.ingestion.gap_fill.get_questdb_watermark", return_value=datetime(2025, 1, 1)), \
         patch("src.liquidationheatmap.ingestion.gap_fill.parquet_glob", return_value="*.parquet"):
        
        con.execute.return_value.fetchone.return_value = [5]
        result = fill_funding_rate(con, mock_questdb, str(tmp_path), "BTCUSDT", True)
        assert result["skipped"] == "dry_run"
        assert result["available"] == 5

def test_validate_gaps_none_watermark(mock_questdb):
    """Test validate_gaps does nothing if watermark is None."""
    validate_gaps(mock_questdb, "BTCUSDT", None)
    mock_questdb.execute_query.assert_not_called()

def test_run_gap_fill_catalog_not_found(tmp_path):
    """Test run_gap_fill raises FileNotFoundError for missing catalog."""
    with pytest.raises(FileNotFoundError, match="CCXT catalog not found"):
        run_gap_fill("dummy_db.duckdb", "/nonexistent/catalog", ["BTCUSDT"])

def test_run_gap_fill_db_not_found(tmp_path):
    """Missing historical DuckDB should fall back to in-memory Parquet reads."""
    # Create fake catalog
    catalog = tmp_path / "catalog"
    catalog.mkdir()

    with patch("src.liquidationheatmap.ingestion.gap_fill.QuestDBService") as mock_qdb_cls, \
         patch("src.liquidationheatmap.ingestion.gap_fill.duckdb.connect") as mock_connect:
        mock_qdb = mock_qdb_cls.return_value
        mock_qdb._sender = object()
        mock_qdb.execute_query.return_value = []

        result = run_gap_fill(str(tmp_path / "nonexistent.db"), str(catalog), ["BTCUSDT"], dry_run=True)

    assert result["total_inserted"] == 0
    mock_connect.assert_called_once_with(":memory:")
