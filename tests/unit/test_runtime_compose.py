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
