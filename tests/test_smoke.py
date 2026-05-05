"""Smoke test to verify test infrastructure works."""


def test_imports():
    """Verify all main dependencies can be imported."""
    import duckdb
    import fastapi
    import pandas
    import plotly
    import pyarrow
    import redis

    assert duckdb.__version__
    assert fastapi.__version__
    assert redis.__version__
    assert plotly.__version__
    assert pandas.__version__
    assert pyarrow.__version__


def test_pytest_fixtures(temp_dir, sample_csv_data, sample_trade_data):
    """Verify pytest fixtures work correctly."""
    assert temp_dir.exists()
    assert "timestamp,price,volume,side" in sample_csv_data
    assert len(sample_trade_data) == 3
    assert sample_trade_data[0]["price"] == 42000.50


def test_test_db_fixture_smoke(test_db):
    """Verify the DuckDB-backed test fixture initializes a working schema."""
    count = test_db.execute("SELECT COUNT(*) FROM information_schema.tables").fetchone()[0]

    assert count >= 3
