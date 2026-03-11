from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path


def capture_coinank_liqmap_capture(request, output_path: Path) -> dict:
    module = import_module("scripts.coinank_screenshot")
    capture_info: dict = {}
    email = os.environ.get("COINANK_USER")
    password = os.environ.get("COINANK_PASSWORD")
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
    return {
        "url": capture_info.get(
            "url",
            module.build_coinank_liqmap_url(request.symbol, request.timeframe, request.exchange or "binance"),
        ),
        "screenshot_path": str(output_path),
        "capture_timestamp": datetime.now(timezone.utc).isoformat(),
        "capture_mode": capture_info.get("method", "screenshot_crop"),
        "capture_info": capture_info,
    }
