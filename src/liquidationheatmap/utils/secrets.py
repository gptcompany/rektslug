"""Helpers for loading secrets from env or the shared dotenvx file."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_SHARED_ENV_FILE = Path("/media/sam/1TB/.env")


def resolve_shared_env_file() -> Path:
    """Return the configured shared env file used for dotenvx lookups."""

    configured_path = os.environ.get("HEATMAP_SHARED_ENV_FILE")
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_SHARED_ENV_FILE


def get_secret(key: str) -> str | None:
    """Load a secret from env or fall back to dotenvx and the shared env file."""

    value = os.environ.get(key)
    if value:
        return value

    shared_env_file = resolve_shared_env_file()
    if not shared_env_file.exists():
        return None

    try:
        result = subprocess.run(
            ["dotenvx", "get", key, "-f", str(shared_env_file)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None
