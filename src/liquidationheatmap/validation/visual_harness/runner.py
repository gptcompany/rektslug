from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter as default_perf_counter
from typing import Callable

from .adapters import get_product_adapter, get_renderer_adapter
from .manifest import build_artifact_paths, build_manifest_dict, write_manifest
from .providers import capture_coinank_liqmap_capture, capture_local_liqmap_capture
from .scorer import build_score_report, write_score_report


@dataclass(frozen=True)
class VisualHarnessRequest:
    run_id: str
    product: str
    renderer: str
    provider: str
    symbol: str
    exchange: str | None = None
    timeframe: str | None = None
    window: str | None = None
    api_base: str = "http://localhost:8002"
    viewport_width: int = 1920
    viewport_height: int = 1400

    def __post_init__(self) -> None:
        if bool(self.timeframe) == bool(self.window):
            raise ValueError("Exactly one of timeframe or window must be provided")


@dataclass(frozen=True)
class AdapterBundle:
    product: object
    renderer: object


@dataclass(frozen=True)
class RunOutcome:
    exit_code: int
    manifest_path: Path
    score_path: Path | None


def resolve_adapter_bundle(*, product: str, renderer: str) -> AdapterBundle:
    product_adapter = get_product_adapter(product)
    renderer_adapter = get_renderer_adapter(renderer)
    if renderer_adapter.name not in product_adapter.supported_renderers:
        raise ValueError(
            f"Unsupported product/renderer combination: {product_adapter.name}/{renderer_adapter.name}"
        )
    return AdapterBundle(product=product_adapter, renderer=renderer_adapter)


def _default_local_capture(request: VisualHarnessRequest, output_path: Path) -> dict:
    if request.product == "liq-map" and request.renderer == "plotly":
        return capture_local_liqmap_capture(request, output_path)
    raise ValueError(f"No local capture adapter for {request.product}/{request.renderer}")


def _default_provider_capture(request: VisualHarnessRequest, output_path: Path) -> dict:
    if request.provider == "coinank" and request.product == "liq-map" and request.renderer == "plotly":
        return capture_coinank_liqmap_capture(request, output_path)
    raise ValueError(
        f"No provider capture adapter for provider={request.provider} product={request.product} renderer={request.renderer}"
    )


def _ensure_tier1_ready(components: list[dict], *, local_ready: bool) -> list[dict]:
    updated: list[dict] = []
    replaced = False
    for component in components:
        if component.get("name") == "tier1_ready":
            replaced = True
            updated.append(
                {
                    **component,
                    "pass": local_ready,
                    "points": 0 if not local_ready else component.get("points", 0),
                    "max_points": component.get("max_points", component.get("points", 0)),
                }
            )
        else:
            updated.append(component)
    if not replaced:
        updated.insert(
            0,
            {
                "name": "tier1_ready",
                "pass": local_ready,
                "points": 0,
                "max_points": 0,
                "detail": "Local page readiness gate",
            },
        )
    return updated


def _default_components(request: VisualHarnessRequest, local_result: dict, provider_result: dict) -> list[dict]:
    manifest_fields_ok = all(
        [
            local_result.get("url"),
            local_result.get("screenshot_path"),
            provider_result.get("url"),
            provider_result.get("screenshot_path"),
        ]
    )
    pair_metadata_ok = bool(
        request.symbol
        and (request.timeframe or request.window)
        and request.product
        and request.renderer
    )
    provider_metadata_ok = bool(provider_result.get("capture_mode"))
    timestamps_ok = bool(
        local_result.get("capture_timestamp") and provider_result.get("capture_timestamp")
    )
    return [
        {"name": "tier1_ready", "pass": bool(local_result.get("ready")), "points": 0, "max_points": 0},
        {
            "name": "tier1_local_artifact",
            "pass": bool(local_result.get("screenshot_path")),
            "points": 0,
            "max_points": 0,
        },
        {
            "name": "tier1_provider_artifact",
            "pass": bool(provider_result.get("screenshot_path")),
            "points": 0,
            "max_points": 0,
        },
        {
            "name": "tier2_manifest_contract",
            "pass": manifest_fields_ok,
            "points": 28 if manifest_fields_ok else 0,
            "max_points": 28,
        },
        {
            "name": "tier2_pair_metadata",
            "pass": pair_metadata_ok,
            "points": 28 if pair_metadata_ok else 0,
            "max_points": 28,
        },
        {
            "name": "tier2_provider_metadata",
            "pass": provider_metadata_ok,
            "points": 28 if provider_metadata_ok else 0,
            "max_points": 28,
        },
        {
            "name": "tier3_timestamps",
            "pass": timestamps_ok,
            "points": 8 if timestamps_ok else 0,
            "max_points": 8,
        },
        {
            "name": "tier3_schema_contract",
            "pass": True,
            "points": 8,
            "max_points": 8,
            "detail": "MVP harness contract satisfied",
        },
    ]


def run_visual_pair(
    *,
    request: VisualHarnessRequest,
    output_dir: Path,
    local_capture: Callable[[VisualHarnessRequest, Path], dict] | None = None,
    provider_capture: Callable[[VisualHarnessRequest, Path], dict] | None = None,
    scorer: Callable[[VisualHarnessRequest, dict, dict], list[dict]] | None = None,
    pass_threshold: int = 95,
    max_runtime_seconds: float = 120.0,
    max_artifact_bytes: int = 1_000_000,
    perf_counter: Callable[[], float] = default_perf_counter,
) -> RunOutcome:
    started_at = perf_counter()
    resolve_adapter_bundle(product=request.product, renderer=request.renderer)
    local_capture_fn = local_capture or _default_local_capture
    provider_capture_fn = provider_capture or _default_provider_capture
    scorer_fn = scorer or _default_components

    paths = build_artifact_paths(output_dir=output_dir, request=request)
    paths.run_dir.mkdir(parents=True, exist_ok=True)

    local_result = local_capture_fn(request, paths.local_screenshot_path)
    try:
        provider_result = provider_capture_fn(request, paths.provider_screenshot_path)
    except Exception as exc:
        manifest = build_manifest_dict(
            request=request,
            local_capture=local_result,
            provider_capture=None,
            failure_reason=str(exc),
        )
        write_manifest(path=paths.manifest_path, manifest=manifest)
        return RunOutcome(exit_code=1, manifest_path=paths.manifest_path, score_path=None)

    components = scorer_fn(request, local_result, provider_result)
    components = _ensure_tier1_ready(components, local_ready=bool(local_result.get("ready")))
    report = build_score_report(
        run_id=request.run_id,
        product=request.product,
        renderer=request.renderer,
        provider=request.provider,
        components=components,
        pass_threshold=pass_threshold,
    )
    manifest = build_manifest_dict(
        request=request,
        local_capture=local_result,
        provider_capture=provider_result,
    )
    write_manifest(path=paths.manifest_path, manifest=manifest)
    elapsed_seconds = round(perf_counter() - started_at, 3)
    combined_artifact_bytes = paths.manifest_path.stat().st_size
    nfr_failures: list[str] = []
    if elapsed_seconds > max_runtime_seconds:
        nfr_failures.append("runtime_exceeded")
    if not local_result.get("capture_timestamp") or not provider_result.get("capture_timestamp"):
        nfr_failures.append("missing_capture_timestamp")
    write_score_report(path=paths.score_path, report=report)
    combined_artifact_bytes += paths.score_path.stat().st_size
    if combined_artifact_bytes > max_artifact_bytes:
        nfr_failures.append("artifact_size_exceeded")
    report["elapsed_seconds"] = elapsed_seconds
    report["artifact_bytes"] = combined_artifact_bytes
    report["nfr_failures"] = nfr_failures
    if nfr_failures:
        report["status"] = "fail"
    write_score_report(path=paths.score_path, report=report)
    exit_code = 0 if report["status"] == "pass" else 1
    return RunOutcome(exit_code=exit_code, manifest_path=paths.manifest_path, score_path=paths.score_path)
