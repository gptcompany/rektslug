"""Tests for shadow pipeline Docker configuration."""

import os
from pathlib import Path

import pytest
import yaml

COMPOSE_FILE = Path("docker-compose.yml")


@pytest.fixture
def compose_config():
    """Load and return docker-compose.yml as dict."""
    assert COMPOSE_FILE.exists(), "docker-compose.yml not found"
    with open(COMPOSE_FILE) as f:
        return yaml.safe_load(f)


def test_redis_service_exists(compose_config):
    """Redis service must be defined in compose."""
    assert "redis" in compose_config["services"]


def test_redis_has_healthcheck(compose_config):
    redis = compose_config["services"]["redis"]
    assert "healthcheck" in redis


def test_shadow_producer_depends_on_redis(compose_config):
    producer = compose_config["services"]["rektslug-shadow-producer"]
    assert "redis" in producer.get("depends_on", {})


def test_shadow_consumer_depends_on_redis(compose_config):
    consumer = compose_config["services"]["rektslug-shadow-consumer"]
    assert "redis" in consumer.get("depends_on", {})


def test_shadow_producer_uses_redis_hostname(compose_config):
    producer = compose_config["services"]["rektslug-shadow-producer"]
    env = producer.get("environment", {})
    assert env.get("REDIS_HOST") == "redis"


def test_shadow_consumer_uses_redis_hostname(compose_config):
    consumer = compose_config["services"]["rektslug-shadow-consumer"]
    env = consumer.get("environment", {})
    assert env.get("REDIS_HOST") == "redis"
    assert env.get("FEEDBACK_DB_PATH") == "/var/lib/rektslug-db/signal_feedback.duckdb"


def test_extra_hosts_in_core_service(compose_config):
    """All core services should resolve host.docker.internal."""
    producer = compose_config["services"]["rektslug-shadow-producer"]
    extra = producer.get("extra_hosts", [])
    assert any("host.docker.internal" in h for h in extra)


def test_shadow_producer_script_exists():
    script = Path("scripts/run-shadow-producer.sh")
    assert script.exists(), "run-shadow-producer.sh not found"
    assert os.access(script, os.X_OK), "run-shadow-producer.sh not executable"


def test_shadow_producer_healthcheck_uses_fresh_expert_manifests(compose_config):
    producer = compose_config["services"]["rektslug-shadow-producer"]
    command = " ".join(producer["healthcheck"]["test"])

    assert "data/cache" not in command
    assert "expert_snapshots/hyperliquid/manifests/BTCUSDT" in command
    assert "expert_snapshots/hyperliquid/manifests/ETHUSDT" in command
    assert "-mmin -10" in command


def test_shadow_producer_uses_shared_runtime_data_dir(compose_config):
    producer = compose_config["services"]["rektslug-shadow-producer"]
    volumes = producer.get("volumes", [])

    assert any("REKTSLUG_DATA_DIR" in volume for volume in volumes)
    assert any("/media/sam/1TB/rektslug/data" in volume for volume in volumes)
    assert any("/app/data" in volume for volume in volumes)


def test_shadow_consumer_enables_ws_stream(compose_config):
    consumer = compose_config["services"]["rektslug-shadow-consumer"]
    command = consumer.get("command", [])
    assert "--enable-ws-stream" in command


def test_feedback_consumer_depends_on_redis(compose_config):
    consumer = compose_config["services"]["rektslug-feedback-consumer"]
    assert "redis" in consumer.get("depends_on", {})


def test_feedback_consumer_uses_redis_hostname(compose_config):
    consumer = compose_config["services"]["rektslug-feedback-consumer"]
    env = consumer.get("environment", {})
    assert env.get("REDIS_HOST") == "redis"
    assert env.get("FEEDBACK_DB_PATH") == "/var/lib/rektslug-db/signal_feedback.duckdb"


def test_feedback_consumer_script_exists():
    script = Path("scripts/run-feedback-consumer.sh")
    assert script.exists(), "run-feedback-consumer.sh not found"
    assert os.access(script, os.X_OK), "run-feedback-consumer.sh not executable"


def test_feedback_consumer_healthcheck_uses_python_probe(compose_config):
    consumer = compose_config["services"]["rektslug-feedback-consumer"]
    healthcheck = consumer.get("healthcheck", {})
    command = healthcheck.get("test", [])
    assert "--healthcheck" in command
    assert "src.liquidationheatmap.signals.feedback" in command


def test_core_services_mount_nautilus_runtime_snapshot(compose_config):
    api = compose_config["services"]["rektslug-api"]
    env = api.get("environment", {})
    volumes = api.get("volumes", [])
    assert (
        env.get("HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH")
        == "/var/lib/nautilus-runtime/portfolio-runtime-snapshot.json"
    )
    assert any("/var/lib/nautilus-runtime:ro" in volume for volume in volumes)
    assert any("/app/specs:ro" in volume for volume in volumes)
    assert env.get("REDIS_HOST") == "redis"
    assert env.get("REDIS_PORT") == "6379"
    assert env.get("REDIS_URL") == "redis://redis:6379/0"
