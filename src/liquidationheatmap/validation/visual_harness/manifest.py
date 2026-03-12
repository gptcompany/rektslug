from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ArtifactPaths:
    run_dir: Path
    local_screenshot_path: Path
    provider_screenshot_path: Path
    manifest_path: Path
    score_path: Path


def _entry_tag(*, timeframe: str | None, window: str | None) -> str:
    if timeframe:
        return timeframe.lower()
    if window:
        return window.lower()
    raise ValueError("Exactly one of timeframe or window must be provided")


def build_artifact_paths(*, output_dir: Path, request) -> ArtifactPaths:
    entry = _entry_tag(timeframe=request.timeframe, window=request.window)
    symbol = request.symbol.lower()
    base_name = (
        f"{request.run_id}_{request.provider}_{request.product}_{request.renderer}_{symbol}_{entry}"
    )
    run_dir = output_dir / request.run_id
    return ArtifactPaths(
        run_dir=run_dir,
        local_screenshot_path=run_dir / f"{base_name}_local.png",
        provider_screenshot_path=run_dir / f"{base_name}_{request.provider}.png",
        manifest_path=run_dir / f"{base_name}_manifest.json",
        score_path=run_dir / f"{base_name}_score.json",
    )


def build_manifest_dict(
    *,
    request,
    local_capture: dict[str, Any] | None,
    provider_capture: dict[str, Any] | None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": request.run_id,
        "product": request.product,
        "renderer": request.renderer,
        "symbol": request.symbol,
        "viewport": {
            "width": request.viewport_width,
            "height": request.viewport_height,
        },
        "local": {
            "url": local_capture.get("url") if local_capture else None,
            "screenshot_path": local_capture.get("screenshot_path") if local_capture else None,
            "capture_timestamp": local_capture.get("capture_timestamp") if local_capture else None,
            "ready": local_capture.get("ready") if local_capture else None,
        },
        "provider": {
            "name": request.provider,
            "url": provider_capture.get("url") if provider_capture else None,
            "screenshot_path": provider_capture.get("screenshot_path") if provider_capture else None,
            "capture_timestamp": provider_capture.get("capture_timestamp") if provider_capture else None,
            "capture_mode": provider_capture.get("capture_mode") if provider_capture else None,
        },
    }
    if request.exchange is not None:
        manifest["exchange"] = request.exchange
    if request.timeframe is not None:
        manifest["timeframe"] = request.timeframe
    if request.window is not None:
        manifest["window"] = request.window
    if local_capture and local_capture.get("local_page_state") is not None:
        manifest["local"]["page_state"] = local_capture["local_page_state"]
    if provider_capture and provider_capture.get("capture_info") is not None:
        manifest["provider"]["capture_info"] = provider_capture["capture_info"]
    if failure_reason is not None:
        manifest["failure_reason"] = failure_reason
    return manifest


def write_manifest(*, path: Path, manifest: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path
