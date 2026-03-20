from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

from src.liquidationheatmap.utils.secrets import get_secret

def capture_coinglass_liqmap_capture(request, output_path: Path) -> dict:
    module = import_module("scripts.capture_provider_api")
    capture_info: dict = {}
    email = get_secret("COINGLASS_USER_LOGIN")
    password = get_secret("COINGLASS_USER_PASSWORD")
    coin = request.symbol.removesuffix("USDT")

    try:
        asyncio.run(
            module.capture_coinglass_liqmap_visual(
                coin=coin,
                timeframe=request.timeframe,
                output_path=output_path,
                headless=True,
                email=email,
                password=password,
                capture_info=capture_info,
            )
        )
    except Exception as exc:
        failure = RuntimeError(f"coinglass capture failed: {exc}")
        failure.capture_context = {
            "url": capture_info.get("url", module.COINGLASS_LIQMAP_PAGE_URL),
            "screenshot_path": str(output_path),
            "capture_timestamp": datetime.now(timezone.utc).isoformat(),
            "capture_mode": capture_info.get("method", "screenshot_viewport"),
            "capture_info": capture_info,
        }
        raise failure from exc

    return {
        "url": capture_info.get("url", module.COINGLASS_LIQMAP_PAGE_URL),
        "screenshot_path": str(output_path),
        "capture_timestamp": datetime.now(timezone.utc).isoformat(),
        "capture_mode": capture_info.get("method", "screenshot_viewport"),
        "capture_info": capture_info,
    }
