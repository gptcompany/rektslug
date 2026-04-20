"""Tests for shadow pipeline Docker configuration."""
import os
import yaml
import pytest
from pathlib import Path

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


def test_extra_hosts_in_core_service(compose_config):
    """All core services should resolve host.docker.internal."""
    producer = compose_config["services"]["rektslug-shadow-producer"]
    extra = producer.get("extra_hosts", [])
    assert any("host.docker.internal" in h for h in extra)


def test_shadow_producer_script_exists():
    script = Path("scripts/run-shadow-producer.sh")
    assert script.exists(), "run-shadow-producer.sh not found"
    assert os.access(script, os.X_OK), "run-shadow-producer.sh not executable"
