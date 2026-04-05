"""Deployment/runtime config tests for the production core stack."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_docker_compose_defines_core_services():
    """docker-compose.yml should define the API, sync, and QuestDB services."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    services = data["services"]
    assert "rektslug-api" in services
    assert "rektslug-sync" in services
    assert "questdb" in services

    api = services["rektslug-api"]
    sync = services["rektslug-sync"]
    questdb = services["questdb"]

    assert api["restart"] == "unless-stopped"
    assert sync["restart"] == "unless-stopped"
    assert questdb["restart"] == "unless-stopped"
    assert "healthcheck" in api
    assert api["ports"] == ["${HEATMAP_PORT:-8002}:8002"]
    assert sync["depends_on"]["rektslug-api"]["condition"] == "service_healthy"
    assert sync["depends_on"]["questdb"]["condition"] == "service_started"
    assert api["depends_on"]["questdb"]["condition"] == "service_started"
    assert api["environment"]["QUESTDB_HOST"] == "${QUESTDB_HOST:-questdb}"
    assert api["environment"]["QUESTDB_PORT"] == "${QUESTDB_PORT:-9009}"
    assert api["environment"]["QUESTDB_PG_PORT"] == "${QUESTDB_PG_PORT:-8812}"


def test_docker_compose_mounts_db_and_ccxt_catalog():
    """The core stack should mount the local DB dir and external ccxt catalog."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    volumes = data["services"]["rektslug-api"]["volumes"]

    assert any("REKTSLUG_DB_DIR" in entry for entry in volumes)
    assert any("HEATMAP_CCXT_CATALOG" in entry for entry in volumes)


def test_core_deploy_workflow_targets_core_code():
    """The deploy workflow should react to core code and container runtime changes."""
    workflow_path = REPO_ROOT / ".github" / "workflows" / "core-deploy.yml"
    text = workflow_path.read_text(encoding="utf-8")

    assert "src/liquidationheatmap/**" in text
    assert "docker-compose.yml" in text
    assert "frontend/**" in text
    assert "docker/build-push-action" in text
    assert "scripts/deploy-core.sh" in text
    assert "scripts/lib/runtime_env.sh" in text
    assert "self-hosted" in text
    assert "deploy-core.sh" in text
    assert 'cd "${GITHUB_WORKSPACE}"' in text
    assert "/media/sam/1TB/rektslug" not in text


def test_deploy_core_uses_shared_env_fallback():
    """deploy-core.sh should reuse shared env or .env.example when checkout .env is absent."""
    script_path = REPO_ROOT / "scripts" / "deploy-core.sh"
    text = script_path.read_text(encoding="utf-8")

    assert '. "$SCRIPT_DIR/lib/runtime_env.sh"' in text
    assert "lh_load_runtime_env host" in text
    assert "SHARED_ENV_FILE" in text
    assert 'ln -sf "${SHARED_ENV_FILE}" .env' in text
    assert 'ln -sf "${PROJECT_DIR}/.env.example" .env' in text
    assert 'rm -f "${PROJECT_DIR}/.env"' in text


def test_runtime_env_loader_supports_hyperliquid_knobs():
    """runtime_env.sh should export Hyperliquid runtime knobs loaded from .env."""
    script_path = REPO_ROOT / "scripts" / "lib" / "runtime_env.sh"
    text = script_path.read_text(encoding="utf-8")

    assert "HEATMAP_HYPERLIQUID_*" in text
    assert "HEATMAP_HL_*" in text
    assert 'export "$key"' in text


def test_precompute_wrapper_uses_runtime_env_and_v3_defaults():
    """The cron wrapper should load runtime env and apply stable v3 defaults."""
    script_path = REPO_ROOT / "scripts" / "run-precompute-hl-sidecar.sh"
    text = script_path.read_text(encoding="utf-8")

    assert '. "$SCRIPT_DIR/lib/runtime_env.sh"' in text
    assert 'CALLER_HEATMAP_SYMBOLS_SHELL="${HEATMAP_SYMBOLS_SHELL-}"' in text
    assert 'CALLER_HEATMAP_SYMBOLS="${HEATMAP_SYMBOLS-}"' in text
    assert "lh_load_runtime_env host" in text
    assert 'export HEATMAP_SYMBOLS_SHELL="$CALLER_HEATMAP_SYMBOLS_SHELL"' in text
    assert 'export HEATMAP_SYMBOLS="$CALLER_HEATMAP_SYMBOLS"' in text
    assert "HEATMAP_HL_TOP_POSITION_OBJECTIVE_BTC:=none" in text
    assert "HEATMAP_HL_TOP_POSITION_TOP_N_BTC:=500" in text
    assert "HEATMAP_HL_TOP_POSITION_SCORE_MODE_ETH:=concentration" in text
    assert 'exec "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/precompute_hl_sidecar.py"' in text


def test_run_ingestion_releases_api_lock_before_precompute_without_warmup():
    """run-ingestion.sh should not reopen DuckDB before heatmap precompute write-path."""
    script_path = REPO_ROOT / "scripts" / "run-ingestion.sh"
    text = script_path.read_text(encoding="utf-8")

    assert 'refresh_api_connections false' in text
    assert 'refresh_api_connections true' in text
    assert '${API_URL}/api/v1/refresh-connections?warmup=${warmup}' in text
