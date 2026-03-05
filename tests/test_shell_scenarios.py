"""Integration tests for shell script scenarios (lock/fallback)."""

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI, Response
from uvicorn import Server, Config
import threading

# Create a minimal test API
app = FastAPI()

@app.post("/api/v1/gap-fill")
async def mock_gap_fill(response: Response):
    code = getattr(app, "mock_code", 200)
    body = getattr(app, "mock_body", {"status": "success", "total_inserted": 42, "duration_seconds": 1.5})
    response.status_code = code
    return body

@app.post("/api/v1/prepare-for-ingestion")
async def mock_prepare():
    return {"status": "success", "connections_closed": 5}

@app.post("/api/v1/refresh-connections")
async def mock_refresh():
    return {"status": "success"}

class TestServer(Server):
    def install_setup(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        super().install_setup()

@pytest.fixture(scope="module")
def api_server():
    """Run a real FastAPI server in a background thread for shell script testing."""
    config = Config(app, host="127.0.0.1", port=8888, log_level="error")
    server = Server(config=config)
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    
    # Wait for server to start
    time.sleep(1)
    yield "http://127.0.0.1:8888"
    server.should_exit = True
    thread.join(timeout=2)

@pytest.fixture
def mock_env(tmp_path, api_server):
    """Set up environment variables for the shell script."""
    env = os.environ.copy()
    env["HEATMAP_ENV_FILE"] = "/dev/null"
    env["HEATMAP_API_URL"] = api_server
    env["HEATMAP_PROJECT_ROOT"] = str(Path(".").resolve())
    env["HEATMAP_DB_PATH"] = str(tmp_path / "test.duckdb")
    env["HEATMAP_CCXT_CATALOG"] = str(tmp_path / "catalog")
    env["HEATMAP_SYMBOLS_SHELL"] = "BTCUSDT ETHUSDT"
    env["HEATMAP_LOG_DIR"] = str(tmp_path / "logs")
    env["REKTSLUG_INTERNAL_TOKEN"] = ""
    
    # Also set the non-prefixed ones just in case
    env["API_URL"] = api_server
    env["PROJECT_DIR"] = env["HEATMAP_PROJECT_ROOT"]
    env["DB_PATH"] = env["HEATMAP_DB_PATH"]
    env["CCXT_CATALOG"] = env["HEATMAP_CCXT_CATALOG"]
    env["SYMBOLS"] = env["HEATMAP_SYMBOLS_SHELL"]
    env["LOG_DIR"] = env["HEATMAP_LOG_DIR"]

    os.makedirs(env["HEATMAP_LOG_DIR"], exist_ok=True)
    os.makedirs(env["HEATMAP_CCXT_CATALOG"], exist_ok=True)
    
    # Create dummy DuckDB tables needed by gap-fill
    import duckdb
    conn = duckdb.connect(env["HEATMAP_DB_PATH"])
    conn.execute("CREATE TABLE IF NOT EXISTS klines_5m_history (open_time TIMESTAMP, symbol VARCHAR, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE, close_time TIMESTAMP, quote_volume DOUBLE, count INTEGER, taker_buy_volume DOUBLE, taker_buy_quote_volume DOUBLE)")
    conn.execute("CREATE TABLE IF NOT EXISTS open_interest_history (id BIGINT, timestamp TIMESTAMP, symbol VARCHAR, open_interest_value DOUBLE, open_interest_contracts DOUBLE, source VARCHAR)")
    conn.execute("CREATE TABLE IF NOT EXISTS funding_rate_history (id BIGINT, timestamp TIMESTAMP, symbol VARCHAR, funding_rate DOUBLE, funding_interval_hours INTEGER)")
    # Add a dummy row to klines to avoid 'no existing klines' warning
    conn.execute("INSERT INTO klines_5m_history (open_time, symbol) VALUES ('2026-01-01 00:00:00', 'BTCUSDT')")
    conn.execute("INSERT INTO open_interest_history (timestamp, symbol) VALUES ('2026-01-01 00:00:00', 'BTCUSDT')")
    conn.execute("INSERT INTO funding_rate_history (timestamp, symbol) VALUES ('2026-01-01 00:00:00', 'BTCUSDT')")
    conn.close()
    
    return env

class TestShellScenarios:
    """Test the shell scripts run-ccxt-gap-fill.sh and run-ingestion.sh."""

    def test_run_gap_fill_success(self, mock_env):
        """Test run-ccxt-gap-fill.sh on HTTP 200."""
        app.mock_code = 200
        app.mock_body = {"status": "success", "total_inserted": 100, "duration_seconds": 2.0}
        
        result = subprocess.run(
            ["bash", "scripts/run-ccxt-gap-fill.sh"],
            env=mock_env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "Gap-fill complete: 100 rows" in result.stdout

    def test_run_gap_fill_already_in_progress(self, mock_env):
        """Test run-ccxt-gap-fill.sh on HTTP 409 (already in progress)."""
        app.mock_code = 409
        app.mock_body = {"status": "conflict", "message": "Already in progress"}
        
        result = subprocess.run(
            ["bash", "scripts/run-ccxt-gap-fill.sh"],
            env=mock_env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "already in progress, skipping" in result.stdout

    def test_run_gap_fill_fallback_on_404(self, mock_env, tmp_path):
        """Test run-ccxt-gap-fill.sh fallback to CLI when API returns 404."""
        app.mock_code = 404
        app.mock_body = {"detail": "Not Found"}
        
        # We need to mock 'uv run' behavior for the fallback
        # But wait, run-ccxt-gap-fill.sh calls 'uv run ... python scripts/fill_gap_from_ccxt.py'
        # To make it succeed, we'd need to mock fill_gap_from_ccxt.py or let it fail gracefully.
        
        # Let's verify it tries to call fallback
        result = subprocess.run(
            ["bash", "scripts/run-ccxt-gap-fill.sh"],
            env=mock_env,
            capture_output=True,
            text=True
        )
        
        # It will likely fail because fill_gap_from_ccxt.py will fail (catalog not found etc)
        # but we want to see it reached the fallback logic.
        assert "falling back to direct CLI execution" in result.stdout

    def test_run_gap_fill_lock_contention_500(self, mock_env):
        """Test run-ccxt-gap-fill.sh handles DuckDB lock message in 500 response."""
        app.mock_code = 500
        app.mock_body = "Could not set lock: conflicting lock held"
        
        result = subprocess.run(
            ["bash", "scripts/run-ccxt-gap-fill.sh"],
            env=mock_env,
            capture_output=True,
            text=True
        )
        
        # Should exit 0 because it's a known non-fatal lock contention
        assert result.returncode == 0
        assert "Gap-fill API lock contention, skipping this cycle" in result.stdout

    def test_run_ingestion_lock_acquisition_failure(self, mock_env):
        """Test run-ingestion.sh failure when DB lock cannot be acquired."""
        # run-ingestion.sh calls prepare_database which calls /api/v1/prepare-for-ingestion
        # and then tests write access.
        
        # Scenario: API is up, but DB is locked by another process
        # We simulate this by making the DB file non-writable
        os.chmod(mock_env["HEATMAP_DB_PATH"], 0o444)
        
        try:
            result = subprocess.run(
                ["bash", "scripts/run-ingestion.sh"],
                env=mock_env,
                capture_output=True,
                text=True
            )
            
            # It should fail after retries
            assert result.returncode != 0
            assert "Cannot acquire database write lock" in result.stdout
        finally:
            os.chmod(mock_env["HEATMAP_DB_PATH"], 0o644)

    def test_run_ingestion_api_unavailable_but_db_ok(self, mock_env):
        """Test run-ingestion.sh succeeds if API is down but DB is accessible."""
        # Shutdown the API server by setting a wrong URL
        mock_env["HEATMAP_API_URL"] = "http://127.0.0.1:9999" # Nothing here
        
        # We'll use a dry-run to make it faster
        result = subprocess.run(
            ["bash", "scripts/run-ingestion.sh", "--dry-run"],
            env=mock_env,
            capture_output=True,
            text=True
        )
        
        # Should still succeed (with warnings about API)
        if result.returncode != 0:
            print(result.stdout)
        assert result.returncode == 0
        assert "API preparation: {\"status\":\"api_unavailable\"}" in result.stdout
        assert "Database write access confirmed" in result.stdout

    def test_daily_aggtrades_tail_gap_window(self):
        """Verify the daily ingestion uses the correct window for aggTrades."""
        # Read the script to verify the window calculation
        script_path = Path("scripts/run-ingestion.sh")
        content = script_path.read_text()
        
        # It should use WEEK_AGO (last 7 days) for daily incremental
        assert "WEEK_AGO=$(date -d \"7 days ago\" +%Y-%m-%d)" in content
        # It should pass WEEK_AGO as start-date to ingest_full_history_n8n.py
        assert "--start-date \"$WEEK_AGO\"" in content
