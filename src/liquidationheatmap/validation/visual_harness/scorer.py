from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .manifest import SCHEMA_VERSION


def _normalize_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for component in components:
        normalized.append(
            {
                "name": component["name"],
                "pass": bool(component["pass"]),
                "points": component.get("points", 0),
                "max_points": component.get("max_points", component.get("points", 0)),
                "detail": component.get("detail"),
            }
        )
    return normalized


def build_score_report(
    *,
    run_id: str,
    product: str,
    renderer: str,
    provider: str,
    components: list[dict[str, Any]],
    pass_threshold: int = 95,
) -> dict[str, Any]:
    normalized = _normalize_components(components)
    tier1_components = [component for component in normalized if component["name"].startswith("tier1_")]
    tier1_pass = all(component["pass"] for component in tier1_components) if tier1_components else True
    max_score = sum(int(component["max_points"]) for component in normalized)
    if not tier1_pass:
        score = 0
    else:
        score = sum(int(component["points"]) for component in normalized)
    status = "pass" if tier1_pass and score >= pass_threshold else "fail"
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "product": product,
        "renderer": renderer,
        "provider": provider,
        "status": status,
        "score": score,
        "max_score": max_score,
        "pass_threshold": pass_threshold,
        "tier1_pass": tier1_pass,
        "components": normalized,
    }


def write_score_report(*, path: Path, report: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
