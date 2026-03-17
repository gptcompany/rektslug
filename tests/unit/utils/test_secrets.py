"""Unit tests for shared secret loading helpers."""

from __future__ import annotations

import subprocess

from src.liquidationheatmap.utils import secrets


def test_get_secret_prefers_environment(monkeypatch):
    monkeypatch.setenv("COINANK_USER", "alice@example.com")

    assert secrets.get_secret("COINANK_USER") == "alice@example.com"


def test_get_secret_uses_configured_shared_env_path(monkeypatch, tmp_path):
    shared_env_file = tmp_path / "custom.env"
    shared_env_file.write_text("unused=1\n", encoding="utf-8")
    monkeypatch.delenv("COINANK_PASSWORD", raising=False)
    monkeypatch.setenv("HEATMAP_SHARED_ENV_FILE", str(shared_env_file))

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="top-secret\n", stderr="")

    monkeypatch.setattr(secrets.subprocess, "run", fake_run)

    assert secrets.get_secret("COINANK_PASSWORD") == "top-secret"
    assert calls == [["dotenvx", "get", "COINANK_PASSWORD", "-f", str(shared_env_file)]]


def test_get_secret_returns_none_when_shared_env_file_is_missing(monkeypatch, tmp_path):
    missing_env_file = tmp_path / "missing.env"
    monkeypatch.delenv("COINANK_PASSWORD", raising=False)
    monkeypatch.setenv("HEATMAP_SHARED_ENV_FILE", str(missing_env_file))

    assert secrets.get_secret("COINANK_PASSWORD") is None
