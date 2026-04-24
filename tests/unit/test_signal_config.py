from src.liquidationheatmap.signals.config import RedisConfig


def test_redis_config_defaults_to_redis_inside_container(monkeypatch):
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.setattr("src.liquidationheatmap.signals.config.Path.exists", lambda self: True)

    config = RedisConfig()

    assert config.host == "redis"


def test_redis_config_uses_env_override(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "custom-redis")
    monkeypatch.setattr("src.liquidationheatmap.signals.config.Path.exists", lambda self: False)

    config = RedisConfig()

    assert config.host == "custom-redis"
