from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path


def _timeframe_days(timeframe: str) -> int:
    mapping = {"1d": 1, "1w": 7}
    try:
        return mapping[timeframe.lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported liq-map timeframe: {timeframe}") from exc


def _profile_for_provider(provider: str) -> str | None:
    mapping = {
        "coinank": "rektslug-ank",
        "coinglass": "rektslug-glass",
    }
    return mapping.get(provider)


def capture_local_liqmap_capture(request, output_path: Path) -> dict:
    module = import_module("scripts.validate_liqmap_visual")
    page_url = module.build_liqmap_page_url(
        api_base=request.api_base,
        exchange=request.exchange or "binance",
        symbol=request.symbol,
        timeframe=_timeframe_days(request.timeframe or ""),
        chart_mode="bar",
        profile=_profile_for_provider(request.provider),
    )
    ready_state = asyncio.run(
        module.capture_local_liqmap_page(
            page_url=page_url,
            output_path=output_path,
            headless=True,
        )
    )
    return {
        "url": page_url,
        "screenshot_path": str(output_path),
        "capture_timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": bool(ready_state.get("ready")),
        "local_page_state": ready_state,
    }
