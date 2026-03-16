from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

_SHARED_ENV = Path("/media/sam/1TB/.env")


def _get_secret(key: str) -> str | None:
    """Load secret from env or fall back to dotenvx."""
    val = os.environ.get(key)
    if val:
        return val
    if not _SHARED_ENV.exists():
        return None
    try:
        result = subprocess.run(
            ["dotenvx", "get", key, "-f", str(_SHARED_ENV)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def capture_coinank_liqmap_capture(request, output_path: Path) -> dict:
    module = import_module("scripts.coinank_screenshot")
    capture_info: dict = {}
    email = _get_secret("COINANK_USER")
    password = _get_secret("COINANK_PASSWORD")
    url = module.build_coinank_liqmap_url(request.symbol, request.timeframe, request.exchange or "binance")
    try:
        asyncio.run(
            module.capture_coinank_liqmap(
                coin=request.symbol,
                timeframe=request.timeframe,
                exchange=request.exchange or "binance",
                output_path=output_path,
                headless=True,
                email=email,
                password=password,
                capture_info=capture_info,
            )
        )
    except Exception as exc:
        failure = RuntimeError(f"coinank capture failed: {exc}")
        failure.capture_context = {
            "url": capture_info.get("url", url),
            "screenshot_path": str(output_path),
            "capture_timestamp": datetime.now(timezone.utc).isoformat(),
            "capture_mode": capture_info.get("method", "screenshot_crop"),
            "capture_info": capture_info,
        }
        raise failure from exc
    return {
        "url": capture_info.get("url", url),
        "screenshot_path": str(output_path),
        "capture_timestamp": datetime.now(timezone.utc).isoformat(),
        "capture_mode": capture_info.get("method", "screenshot_crop"),
        "capture_info": capture_info,
    }
