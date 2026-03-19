"""Integration tests for shell script scenarios using curl mocking (non-interactive)."""

import os
import signal
import subprocess
import time
import pytest
from pathlib import Path

@pytest.fixture
def mock_curl(tmp_path):
    """Create a mock curl script to intercept API calls."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    curl_script = mock_bin / "curl"
    
    # Improved mock curl that correctly handles the body + http_code pattern
    # ensuring they are on separate lines for tail -n1 to work.
    script_content = """#!/bin/bash
# Mock curl
RESPONSE_BODY='{"status": "success"}'
HTTP_CODE="200"

if [[ "$*" == *"gap-fill"* ]]; then
    RESPONSE_BODY='{"status": "success", "total_inserted": 42}'
elif [[ "$*" == *"prepare-for-ingestion"* ]]; then
    RESPONSE_BODY='{"status": "success", "connections_closed": 5}'
fi

if [ -f "$MOCK_CURL_RESPONSE_FILE" ]; then
    RESPONSE_BODY=$(cat "$MOCK_CURL_RESPONSE_FILE")
    if [[ "$RESPONSE_BODY" == *"conflicting lock held"* ]]; then
        HTTP_CODE="500"
    fi
fi

# If -w "%{http_code}" is present, output body + code on new line
if [[ "$*" == *"%{http_code}"* ]]; then
    echo "$RESPONSE_BODY"
    echo "$HTTP_CODE"
else
    echo "$RESPONSE_BODY"
fi
exit 0
"""
    curl_script.write_text(script_content)
    curl_script.chmod(0o755)
    return mock_bin

@pytest.fixture
def mock_env(tmp_path, mock_curl):
    """Set up environment variables for the shell script."""
    env = os.environ.copy()
    env["PATH"] = f"{mock_curl}:{env['PATH']}"
    env["HEATMAP_ENV_FILE"] = "/dev/null"
    env["HEATMAP_API_URL"] = "http://mock-api"
    env["HEATMAP_PROJECT_ROOT"] = str(Path(".").resolve())
    env["HEATMAP_DB_PATH"] = str(tmp_path / "test.duckdb")
    env["HEATMAP_CCXT_CATALOG"] = str(tmp_path / "catalog")
    env["HEATMAP_SYMBOLS_SHELL"] = "BTCUSDT"
    env["HEATMAP_LOG_DIR"] = str(tmp_path / "logs")
    env["REKTSLUG_INTERNAL_TOKEN"] = ""
    
    os.makedirs(env["HEATMAP_LOG_DIR"], exist_ok=True)
    os.makedirs(env["HEATMAP_CCXT_CATALOG"], exist_ok=True)
    
    import duckdb
    conn = duckdb.connect(env["HEATMAP_DB_PATH"])
    conn.execute("CREATE TABLE IF NOT EXISTS klines_5m_history (open_time TIMESTAMP, symbol VARCHAR, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE, close_time TIMESTAMP, quote_volume DOUBLE, count INTEGER, taker_buy_volume DOUBLE, taker_buy_quote_volume DOUBLE)")
    conn.execute("CREATE TABLE IF NOT EXISTS open_interest_history (id BIGINT, timestamp TIMESTAMP, symbol VARCHAR, open_interest_value DOUBLE, open_interest_contracts DOUBLE, source VARCHAR)")
    conn.execute("CREATE TABLE IF NOT EXISTS funding_rate_history (id BIGINT, timestamp TIMESTAMP, symbol VARCHAR, funding_rate DOUBLE, funding_interval_hours INTEGER)")
    conn.execute("INSERT INTO klines_5m_history (open_time, symbol) VALUES ('2026-01-01 00:00:00', 'BTCUSDT')")
    conn.execute("INSERT INTO open_interest_history (timestamp, symbol) VALUES ('2026-01-01 00:00:00', 'BTCUSDT')")
    conn.execute("INSERT INTO funding_rate_history (timestamp, symbol) VALUES ('2026-01-01 00:00:00', 'BTCUSDT')")
    conn.close()
    
    return env

class TestShellScenariosMocked:
    """Test shell scripts using curl mocking instead of a live server."""

    def test_run_gap_fill_success(self, mock_env):
        """Test success path."""
        result = subprocess.run(
            ["bash", "scripts/run-ccxt-gap-fill.sh"],
            env=mock_env, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Gap-fill complete" in result.stdout

    def test_run_gap_fill_lock_contention(self, mock_env, tmp_path):
        """Test non-fatal lock contention handling."""
        resp_file = tmp_path / "resp.json"
        resp_file.write_text("Could not set lock: conflicting lock held")
        mock_env["MOCK_CURL_RESPONSE_FILE"] = str(resp_file)

        result = subprocess.run(
            ["bash", "scripts/run-ccxt-gap-fill.sh"],
            env=mock_env, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "SKIPPED_LOCK_CONTENTION:" in result.stdout
        assert "lock contention" in result.stdout.lower()

    def test_run_ingestion_dry_run(self, mock_env):
        """Test main ingestion script in dry-run mode."""
        result = subprocess.run(
            ["bash", "scripts/run-ingestion.sh", "--dry-run"],
            env=mock_env, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Database write access confirmed" in result.stdout

    def test_run_ingestion_daily_lock_contention_skips_cleanly(self, mock_env, tmp_path):
        """Daily ingestion should skip safely when another writer holds the DB lock."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        uv_script = mock_bin / "uv"
        uv_script.write_text(
            """#!/bin/bash
if [[ "$*" == *"cleanup_duckdb_locks.py"* ]]; then
    exit 0
fi
if [[ "$*" == *"python -c"* ]]; then
    echo "Lock test failed: Could not set lock on file" >&2
    exit 1
fi
exit 0
"""
        )
        uv_script.chmod(0o755)
        mock_env["PATH"] = f"{mock_bin}:{mock_env['PATH']}"

        result = subprocess.run(
            ["bash", "scripts/run-ingestion.sh"],
            env=mock_env, capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "SKIPPED_LOCK_CONTENTION: Cannot acquire database write lock" in result.stdout
        assert "SKIPPED_LOCK_CONTENTION: Daily ingestion skipped before writes" in result.stdout

    def test_run_ingestion_full_lock_contention_still_fails(self, mock_env, tmp_path):
        """Full ingestion should still fail hard on database lock contention."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        uv_script = mock_bin / "uv"
        uv_script.write_text(
            """#!/bin/bash
if [[ "$*" == *"cleanup_duckdb_locks.py"* ]]; then
    exit 0
fi
if [[ "$*" == *"python -c"* ]]; then
    echo "Lock test failed: Could not set lock on file" >&2
    exit 1
fi
exit 0
"""
        )
        uv_script.chmod(0o755)
        mock_env["PATH"] = f"{mock_bin}:{mock_env['PATH']}"

        result = subprocess.run(
            ["bash", "scripts/run-ingestion.sh", "--full"],
            env=mock_env, capture_output=True, text=True
        )

        assert result.returncode == 1
        assert "SKIPPED_LOCK_CONTENTION: Cannot acquire database write lock" in result.stdout

    def test_run_ingestion_restores_sync_container_on_sigterm(self, mock_env, tmp_path):
        """SIGTERM should restore rektslug-sync if this run stopped it."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        docker_state = tmp_path / "docker-state.txt"
        docker_state.write_text("true")
        docker_events = tmp_path / "docker-events.log"
        ready_flag = tmp_path / "ingest-ready.flag"

        docker_script = mock_bin / "docker"
        docker_script.write_text(
            """#!/bin/bash
set -euo pipefail
state_file="${MOCK_DOCKER_STATE_FILE:?}"
events_file="${MOCK_DOCKER_EVENTS_FILE:?}"
cmd="$1"
shift || true

case "$cmd" in
  inspect)
    cat "$state_file"
    ;;
  stop)
    echo "stop" >> "$events_file"
    echo "false" > "$state_file"
    ;;
  start)
    echo "start" >> "$events_file"
    echo "true" > "$state_file"
    ;;
  *)
    echo "unexpected docker command: $cmd" >&2
    exit 1
    ;;
esac
"""
        )
        docker_script.chmod(0o755)

        uv_script = mock_bin / "uv"
        uv_script.write_text(
            """#!/bin/bash
if [[ "$*" == *"cleanup_duckdb_locks.py"* ]]; then
    exit 0
fi
if [[ "$*" == *"python -c"* ]]; then
    exit 0
fi
if [[ "$*" == *"ingest_full_history_n8n.py"* ]]; then
    touch "${MOCK_INGEST_READY_FLAG:?}"
    sleep 30
    exit 0
fi
exit 0
"""
        )
        uv_script.chmod(0o755)

        mock_env["PATH"] = f"{mock_bin}:{mock_env['PATH']}"
        mock_env["MOCK_DOCKER_STATE_FILE"] = str(docker_state)
        mock_env["MOCK_DOCKER_EVENTS_FILE"] = str(docker_events)
        mock_env["MOCK_INGEST_READY_FLAG"] = str(ready_flag)

        proc = subprocess.Popen(
            ["bash", "scripts/run-ingestion.sh", "--dry-run"],
            env=mock_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

        try:
            deadline = time.time() + 10
            while not ready_flag.exists():
                if proc.poll() is not None:
                    raise AssertionError(proc.stdout.read())
                if time.time() >= deadline:
                    raise AssertionError("Timed out waiting for mocked ingestion to start")
                time.sleep(0.1)

            os.killpg(proc.pid, signal.SIGTERM)
            stdout, _ = proc.communicate(timeout=10)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)

        assert proc.returncode != 0
        assert docker_state.read_text().strip() == "true"
        assert docker_events.read_text().strip().splitlines() == ["stop", "start"]
        assert "Ingesting BTCUSDT aggTrades..." in stdout

    def test_run_ingestion_fails_when_sync_restart_fails(self, mock_env, tmp_path):
        """Restart failures must fail the job instead of logging success."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        docker_state = tmp_path / "docker-state.txt"
        docker_state.write_text("true")
        docker_events = tmp_path / "docker-events.log"

        docker_script = mock_bin / "docker"
        docker_script.write_text(
            """#!/bin/bash
set -euo pipefail
state_file="${MOCK_DOCKER_STATE_FILE:?}"
events_file="${MOCK_DOCKER_EVENTS_FILE:?}"
cmd="$1"
shift || true

case "$cmd" in
  inspect)
    cat "$state_file"
    ;;
  stop)
    echo "stop" >> "$events_file"
    echo "false" > "$state_file"
    ;;
  start)
    echo "start" >> "$events_file"
    exit 1
    ;;
  *)
    echo "unexpected docker command: $cmd" >&2
    exit 1
    ;;
esac
"""
        )
        docker_script.chmod(0o755)

        uv_script = mock_bin / "uv"
        uv_script.write_text(
            """#!/bin/bash
exit 0
"""
        )
        uv_script.chmod(0o755)

        mock_env["PATH"] = f"{mock_bin}:{mock_env['PATH']}"
        mock_env["MOCK_DOCKER_STATE_FILE"] = str(docker_state)
        mock_env["MOCK_DOCKER_EVENTS_FILE"] = str(docker_events)

        result = subprocess.run(
            ["bash", "scripts/run-ingestion.sh", "--dry-run"],
            env=mock_env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "ERROR: Failed to restart rektslug-sync" in result.stdout
        assert "Sync container restart: FAILED" in result.stdout
