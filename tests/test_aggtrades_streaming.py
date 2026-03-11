"""Tests for streaming aggTrades ingestion."""

from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from src.liquidationheatmap.ingestion import aggtrades_streaming
from src.liquidationheatmap.ingestion.aggtrades_streaming import (
    _validate_symbol,
    get_aggtrades_files,
    load_aggtrades_streaming,
)


def _fetchone_result(value):
    result = MagicMock()
    result.fetchone.return_value = value
    return result


@pytest.mark.parametrize("symbol", [None, "", 123])
def test_validate_symbol_rejects_empty_or_non_string(symbol):
    """Should reject missing and non-string symbols."""
    with pytest.raises(ValueError, match="Invalid symbol"):
        _validate_symbol(symbol)


def test_validate_symbol_normalizes_case_and_whitespace():
    """Should uppercase and trim valid symbols."""
    assert _validate_symbol("  btcusdt  ") == "BTCUSDT"


@pytest.mark.parametrize("symbol", ["BTC-USD", "../BTCUSDT", "BTCUSD"])
def test_validate_symbol_rejects_invalid_format(symbol):
    """Should reject symbols that do not match the expected pattern."""
    with pytest.raises(ValueError, match="Invalid symbol format"):
        _validate_symbol(symbol)


def test_validate_symbol_rejects_non_whitelisted_symbol():
    """Should reject syntactically valid but unsupported symbols."""
    with pytest.raises(ValueError, match="not in allowed list"):
        _validate_symbol("LTCUSDT")


def test_get_aggtrades_files_raises_for_missing_directory(tmp_path):
    """Should fail if the aggTrades directory is absent."""
    with pytest.raises(FileNotFoundError, match="aggTrades directory not found"):
        get_aggtrades_files(tmp_path, "BTCUSDT", "2024-01-01", "2024-01-01")


def test_get_aggtrades_files_returns_existing_files_in_range(tmp_path):
    """Should return only files that exist within date range."""
    aggtrades_dir = tmp_path / "BTCUSDT" / "aggTrades"
    aggtrades_dir.mkdir(parents=True)

    (aggtrades_dir / "BTCUSDT-aggTrades-2024-01-01.csv").touch()
    (aggtrades_dir / "BTCUSDT-aggTrades-2024-01-02.csv").touch()
    (aggtrades_dir / "BTCUSDT-aggTrades-2024-01-05.csv").touch()

    files = get_aggtrades_files(tmp_path, "BTCUSDT", "2024-01-01", "2024-01-03")

    assert len(files) == 2
    assert files[0].name == "BTCUSDT-aggTrades-2024-01-01.csv"
    assert files[1].name == "BTCUSDT-aggTrades-2024-01-02.csv"


def test_load_aggtrades_streaming_returns_zero_when_no_files(monkeypatch):
    """Should exit early when the date range resolves to no CSV files."""
    conn = MagicMock()
    monkeypatch.setattr(aggtrades_streaming, "get_aggtrades_files", lambda *args: [])

    total = load_aggtrades_streaming(
        conn,
        "/tmp/data",
        "BTCUSDT",
        "2024-01-01",
        "2024-01-01",
    )

    assert total == 0
    assert conn.execute.call_count == 3


def test_load_aggtrades_streaming_ingests_header_format(monkeypatch):
    """Should ingest a header-based CSV file successfully."""
    file_path = Path("/tmp/BTCUSDT-aggTrades-2024-01-01.csv")
    conn = MagicMock()
    sleep_calls = []

    monkeypatch.setattr(aggtrades_streaming, "get_aggtrades_files", lambda *args: [file_path])
    monkeypatch.setattr(aggtrades_streaming.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    conn.execute.side_effect = [
        None,
        None,
        None,
        _fetchone_result((0,)),
        _fetchone_result((100,)),
        None,
        _fetchone_result((100,)),
        _fetchone_result((100,)),
    ]

    total = load_aggtrades_streaming(
        conn,
        "/tmp/data",
        "BTCUSDT",
        "2024-01-01",
        "2024-01-01",
        throttle_ms=10,
    )

    assert total == 100
    assert sleep_calls == [0.01]
    executed_queries = [call.args[0] for call in conn.execute.call_args_list]
    assert "SET memory_limit = '32GB'" in executed_queries[0]
    assert any("header=true" in query for query in executed_queries if isinstance(query, str))


def test_load_aggtrades_streaming_falls_back_to_no_header(monkeypatch):
    """Should switch to the no-header parser when binder errors indicate the old format."""
    file_path = Path("/tmp/BTCUSDT-aggTrades-2024-01-01.csv")
    conn = MagicMock()

    monkeypatch.setattr(aggtrades_streaming, "get_aggtrades_files", lambda *args: [file_path])
    monkeypatch.setattr(aggtrades_streaming.time, "sleep", lambda *_args: None)

    conn.execute.side_effect = [
        None,
        None,
        None,
        _fetchone_result((0,)),
        duckdb.BinderException("column transact_time not found"),
        _fetchone_result((80,)),
        None,
        _fetchone_result((80,)),
        _fetchone_result((80,)),
    ]

    total = load_aggtrades_streaming(
        conn,
        "/tmp/data",
        "BTCUSDT",
        "2024-01-01",
        "2024-01-01",
        throttle_ms=0,
    )

    assert total == 80
    executed_queries = [call.args[0] for call in conn.execute.call_args_list]
    assert any("header=false" in query for query in executed_queries if isinstance(query, str))


def test_load_aggtrades_streaming_skips_files_with_unexpected_errors(monkeypatch):
    """Should skip unreadable files and continue the overall ingestion run."""
    file_path = Path("/tmp/BTCUSDT-aggTrades-2024-01-01.csv")
    conn = MagicMock()

    monkeypatch.setattr(aggtrades_streaming, "get_aggtrades_files", lambda *args: [file_path])
    monkeypatch.setattr(aggtrades_streaming.time, "sleep", lambda *_args: None)

    conn.execute.side_effect = [
        None,
        None,
        None,
        _fetchone_result((5,)),
        RuntimeError("broken csv"),
        _fetchone_result((5,)),
    ]

    total = load_aggtrades_streaming(
        conn,
        "/tmp/data",
        "BTCUSDT",
        "2024-01-01",
        "2024-01-01",
        throttle_ms=0,
    )

    assert total == 0


def test_load_aggtrades_streaming_checkpoints_and_reports_complete_database(monkeypatch):
    """Should checkpoint periodically and report when data already exists."""
    file_path = Path("/tmp/BTCUSDT-aggTrades-2024-01-01.csv")
    conn = MagicMock()
    sleep_calls = []

    monkeypatch.setattr(aggtrades_streaming, "get_aggtrades_files", lambda *args: [file_path])
    monkeypatch.setattr(aggtrades_streaming.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    conn.execute.side_effect = [
        None,
        None,
        None,
        _fetchone_result((10,)),
        _fetchone_result((50,)),
        None,
        _fetchone_result((10,)),
        None,
        _fetchone_result((10,)),
    ]

    total = load_aggtrades_streaming(
        conn,
        "/tmp/data",
        "BTCUSDT",
        "2024-01-01",
        "2024-01-01",
        throttle_ms=0,
        batch_checkpoint_files=1,
    )

    assert total == 0
    assert sleep_calls == [1]
    executed_queries = [call.args[0] for call in conn.execute.call_args_list]
    assert "CHECKPOINT" in executed_queries
