from __future__ import annotations

from pathlib import Path

from scripts.compare_provider_liquidations import NormalizedDataset, build_report
from src.liquidationheatmap.validation.provider_profiles import get_provider_profile


def test_counterflow_profile_is_explicit_data_source_and_visual_reference():
    profile = get_provider_profile("bitcoincounterflow")

    assert profile.display_name == "Bitcoin CounterFlow"
    assert profile.default_renderer_adapter == "lightweight"
    assert profile.data_comparison_ready is True
    assert profile.visual_reference is True
    assert profile.roles == frozenset({"data-source", "visual-reference"})


def test_unknown_provider_profile_falls_back_to_explicit_unknown_identity():
    profile = get_provider_profile("mystery-provider")

    assert profile.name == "mystery-provider"
    assert profile.display_name == "mystery-provider"
    assert profile.default_renderer_adapter is None
    assert profile.data_comparison_ready is False
    assert profile.visual_reference is False
    assert profile.roles == frozenset({"unknown"})


def test_build_report_emits_provider_profiles_separately_from_dataset_payloads():
    datasets = {
        "bitcoincounterflow": NormalizedDataset(
            provider="bitcoincounterflow",
            source_url="https://api.bitcoincounterflow.com/api/liquidations",
            saved_file="/tmp/counterflow.json",
            dataset_kind="liquidations_timeseries",
            structure="time_candles",
            unit="usd_notional",
            product="liquidations-timeseries",
            symbol="BTCUSDT",
            exchange="binance",
            timeframe="1h",
            bucket_count=24,
            total_long=1000.0,
            total_short=900.0,
            peak_long=120.0,
            peak_short=110.0,
            time_step_median_ms=3600000.0,
            notes=["Synthetic test dataset"],
            parse_score=100,
        )
    }

    report = build_report(
        manifest_paths=[Path("/tmp/manifest.json")],
        datasets=datasets,
        skipped_by_provider={},
    )

    assert "provider_profiles" in report
    assert "bitcoincounterflow" in report["provider_profiles"]
    assert report["provider_profiles"]["bitcoincounterflow"]["default_renderer_adapter"] == "lightweight"
    assert report["provider_profiles"]["bitcoincounterflow"]["roles"] == [
        "data-source",
        "visual-reference",
    ]
    assert report["providers"]["bitcoincounterflow"]["provider"] == "bitcoincounterflow"
    assert "default_renderer_adapter" not in report["providers"]["bitcoincounterflow"]
