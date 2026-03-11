from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.liquidationheatmap.validation.visual_harness.manifest import (
    SCHEMA_VERSION,
    build_artifact_paths,
)
from src.liquidationheatmap.validation.visual_harness.runner import (
    VisualHarnessRequest,
    resolve_adapter_bundle,
    run_visual_pair,
)
from src.liquidationheatmap.validation.visual_harness.scorer import build_score_report


@pytest.fixture()
def harness_request() -> VisualHarnessRequest:
    return VisualHarnessRequest(
        run_id="run-001",
        product="liq-map",
        renderer="plotly",
        provider="coinank",
        symbol="BTCUSDT",
        exchange="binance",
        timeframe="1d",
    )


def _local_capture_ready(_request: VisualHarnessRequest, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("local")
    return {
        "url": "http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d",
        "screenshot_path": str(output_path),
        "capture_timestamp": "2026-03-11T10:00:00Z",
        "ready": True,
        "local_page_state": {
            "hasPlotlyGlobal": True,
            "hasPlotRoot": True,
            "hasMainSvg": True,
        },
    }


def _local_capture_not_ready(_request: VisualHarnessRequest, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("local")
    return {
        "url": "http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d",
        "screenshot_path": str(output_path),
        "capture_timestamp": "2026-03-11T10:00:00Z",
        "ready": False,
        "local_page_state": {
            "hasPlotlyGlobal": True,
            "levels_request_failures": [{"status": 503}],
            "failure_reason": "levels_request_failed",
        },
    }


def _provider_capture_ok(_request: VisualHarnessRequest, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("provider")
    return {
        "url": "https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d",
        "screenshot_path": str(output_path),
        "capture_timestamp": "2026-03-11T10:00:05Z",
        "capture_mode": "screenshot_crop",
    }


def _provider_capture_unreachable(_request: VisualHarnessRequest, _output_path: Path):
    raise RuntimeError("provider unreachable")


def _passing_scorer(_request, _local_capture, _provider_capture):
    return [
        {"name": "tier1_ready", "pass": True, "points": 0, "max_points": 0},
        {"name": "tier2_layout", "pass": True, "points": 84, "max_points": 84},
        {"name": "tier3_metrics", "pass": True, "points": 16, "max_points": 16},
    ]


def _threshold_failing_scorer(_request, _local_capture, _provider_capture):
    return [
        {"name": "tier1_ready", "pass": True, "points": 0, "max_points": 0},
        {"name": "tier2_layout", "pass": True, "points": 80, "max_points": 84},
        {"name": "tier3_metrics", "pass": True, "points": 14, "max_points": 16},
    ]


def test_manifest_json_validates_against_required_field_schema(
    tmp_path: Path,
    harness_request: VisualHarnessRequest,
):
    outcome = run_visual_pair(
        request=harness_request,
        output_dir=tmp_path,
        local_capture=_local_capture_ready,
        provider_capture=_provider_capture_ok,
        scorer=_passing_scorer,
    )

    manifest = json.loads(outcome.manifest_path.read_text(encoding="utf-8"))

    assert outcome.exit_code == 0
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["run_id"] == "run-001"
    assert manifest["product"] == "liq-map"
    assert manifest["renderer"] == "plotly"
    assert manifest["symbol"] == "BTCUSDT"
    assert manifest["exchange"] == "binance"
    assert manifest["timeframe"] == "1d"
    assert "window" not in manifest
    assert manifest["viewport"] == {"width": 1920, "height": 1400}
    assert manifest["local"]["ready"] is True
    assert manifest["local"]["capture_timestamp"]
    assert manifest["local"]["page_state"]["hasPlotRoot"] is True
    assert manifest["provider"]["name"] == "coinank"
    assert manifest["provider"]["capture_mode"] == "screenshot_crop"
    assert manifest["provider"]["capture_timestamp"]


def test_adapter_dispatch_routes_product_renderer_to_correct_handler():
    bundle = resolve_adapter_bundle(product="liq-map", renderer="plotly")

    assert bundle.product.name == "liq-map"
    assert bundle.renderer.name == "plotly"


def test_window_requests_fail_fast_for_current_timeframe_only_adapters():
    with pytest.raises(ValueError, match="window-based visual harness requests are not supported"):
        VisualHarnessRequest(
            run_id="run-001",
            product="liq-map",
            renderer="plotly",
            provider="coinank",
            symbol="BTCUSDT",
            exchange="binance",
            window="48h",
        )


def test_unsupported_product_renderer_combination_fails_before_capture(tmp_path: Path):
    request = VisualHarnessRequest(
        run_id="run-001",
        product="liq-map",
        renderer="lightweight",
        provider="coinank",
        symbol="BTCUSDT",
        exchange="binance",
        timeframe="1d",
    )

    with pytest.raises(ValueError, match="Unsupported product/renderer combination"):
        run_visual_pair(
            request=request,
            output_dir=tmp_path,
            local_capture=_local_capture_ready,
            provider_capture=_provider_capture_ok,
            scorer=_passing_scorer,
        )


def test_local_chart_not_ready_returns_ready_false_tier1_fail_and_score_zero(
    tmp_path: Path,
    harness_request: VisualHarnessRequest,
):
    outcome = run_visual_pair(
        request=harness_request,
        output_dir=tmp_path,
        local_capture=_local_capture_not_ready,
        provider_capture=_provider_capture_ok,
        scorer=_passing_scorer,
    )

    report = json.loads(outcome.score_path.read_text(encoding="utf-8"))
    manifest = json.loads(outcome.manifest_path.read_text(encoding="utf-8"))

    assert outcome.exit_code == 1
    assert manifest["local"]["ready"] is False
    assert report["tier1_pass"] is False
    assert report["score"] == 0


def test_provider_unreachable_returns_non_zero_and_partial_manifest_with_failure_reason(
    tmp_path: Path,
    harness_request: VisualHarnessRequest,
):
    outcome = run_visual_pair(
        request=harness_request,
        output_dir=tmp_path,
        local_capture=_local_capture_ready,
        provider_capture=_provider_capture_unreachable,
        scorer=_passing_scorer,
    )

    manifest = json.loads(outcome.manifest_path.read_text(encoding="utf-8"))

    assert outcome.exit_code == 1
    assert outcome.score_path is None
    assert manifest["failure_reason"] == "provider unreachable"
    assert manifest["provider"]["name"] == "coinank"


def test_score_threshold_gate_returns_non_zero_when_score_below_pass_threshold(
    tmp_path: Path,
    harness_request: VisualHarnessRequest,
):
    outcome = run_visual_pair(
        request=harness_request,
        output_dir=tmp_path,
        local_capture=_local_capture_ready,
        provider_capture=_provider_capture_ok,
        scorer=_threshold_failing_scorer,
    )

    report = json.loads(outcome.score_path.read_text(encoding="utf-8"))

    assert outcome.exit_code == 1
    assert report["pass_threshold"] == 95
    assert report["score"] == 94
    assert report["status"] == "fail"


def test_re_running_same_matrix_entry_with_same_run_id_produces_identical_artifact_paths_and_schema_version(
    tmp_path: Path,
    harness_request: VisualHarnessRequest,
):
    paths_a = build_artifact_paths(output_dir=tmp_path, request=harness_request)
    paths_b = build_artifact_paths(output_dir=tmp_path, request=harness_request)

    assert paths_a == paths_b
    assert paths_a.manifest_path.name == paths_b.manifest_path.name
    assert SCHEMA_VERSION == "1.0"


def test_score_report_components_follow_declared_schema():
    report = build_score_report(
        run_id="run-001",
        product="liq-map",
        renderer="plotly",
        provider="coinank",
        components=_passing_scorer(None, None, None),
    )

    component = report["components"][0]
    assert set(component) >= {"name", "pass", "points", "max_points"}


def test_default_runner_scoring_passes_when_capture_contract_is_complete(
    tmp_path: Path,
    harness_request: VisualHarnessRequest,
):
    outcome = run_visual_pair(
        request=harness_request,
        output_dir=tmp_path,
        local_capture=_local_capture_ready,
        provider_capture=_provider_capture_ok,
    )

    report = json.loads(outcome.score_path.read_text(encoding="utf-8"))

    assert outcome.exit_code == 0
    assert report["score"] == 100
    assert report["status"] == "pass"


def test_local_provider_wrapper_reuses_validate_liqmap_visual(monkeypatch, tmp_path: Path, harness_request):
    from src.liquidationheatmap.validation.visual_harness.providers.local import capture_local_liqmap_capture

    async def _capture_local_liqmap_page(*, page_url, output_path, headless):
        output_path.write_text("local")
        assert page_url.endswith("/chart/derivatives/liq-map/binance/btcusdt/1d")
        assert headless is True
        return {"ready": True}

    fake_module = SimpleNamespace(
        build_liqmap_page_url=lambda **_kwargs: "http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d",
        capture_local_liqmap_page=_capture_local_liqmap_page,
    )
    monkeypatch.setattr(
        "src.liquidationheatmap.validation.visual_harness.providers.local.import_module",
        lambda _name: fake_module,
    )

    result = capture_local_liqmap_capture(harness_request, tmp_path / "local.png")

    assert result["ready"] is True
    assert result["url"].endswith("/chart/derivatives/liq-map/binance/btcusdt/1d")


def test_coinank_provider_wrapper_tracks_capture_mode(monkeypatch, tmp_path: Path, harness_request):
    from src.liquidationheatmap.validation.visual_harness.providers.coinank import capture_coinank_liqmap_capture

    async def _capture_coinank_liqmap(**kwargs):
        kwargs["output_path"].write_text("provider")
        kwargs["capture_info"]["method"] = "native_download"
        kwargs["capture_info"]["url"] = "https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d"
        return kwargs["output_path"]

    fake_module = SimpleNamespace(
        capture_coinank_liqmap=_capture_coinank_liqmap,
        build_coinank_liqmap_url=lambda *_args, **_kwargs: "https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d",
    )
    monkeypatch.setattr(
        "src.liquidationheatmap.validation.visual_harness.providers.coinank.import_module",
        lambda _name: fake_module,
    )

    result = capture_coinank_liqmap_capture(harness_request, tmp_path / "provider.png")

    assert result["capture_mode"] == "native_download"
    assert result["url"].endswith("/chart/derivatives/liq-map/binance/btcusdt/1d")


def test_runner_fails_when_combined_artifact_size_exceeds_limit(
    tmp_path: Path,
    harness_request: VisualHarnessRequest,
):
    outcome = run_visual_pair(
        request=harness_request,
        output_dir=tmp_path,
        local_capture=_local_capture_ready,
        provider_capture=_provider_capture_ok,
        scorer=_passing_scorer,
        max_artifact_bytes=100,
    )

    report = json.loads(outcome.score_path.read_text(encoding="utf-8"))

    assert outcome.exit_code == 1
    assert "artifact_size_exceeded" in report["nfr_failures"]


def test_runner_fails_when_runtime_budget_is_exceeded(
    tmp_path: Path,
    harness_request: VisualHarnessRequest,
):
    clock = iter([0.0, 121.0]).__next__

    outcome = run_visual_pair(
        request=harness_request,
        output_dir=tmp_path,
        local_capture=_local_capture_ready,
        provider_capture=_provider_capture_ok,
        scorer=_passing_scorer,
        max_runtime_seconds=120,
        perf_counter=clock,
    )

    report = json.loads(outcome.score_path.read_text(encoding="utf-8"))

    assert outcome.exit_code == 1
    assert report["elapsed_seconds"] == 121.0
    assert "runtime_exceeded" in report["nfr_failures"]
