"""Unit tests for spec-019 Coinglass calibration helpers."""

import json
from pathlib import Path

from scripts.run_glass_calibration import (
    GLASS_IMPROVEMENT_THRESHOLDS,
    normalize_report_timeframe,
    run_local_profile_capture,
)


def test_normalize_report_timeframe_maps_coinglass_labels():
    assert normalize_report_timeframe("1 day") == "1d"
    assert normalize_report_timeframe("7 day") == "1w"
    assert normalize_report_timeframe("1d") == "1d"


def test_glass_thresholds_relax_bucket_overlap_only():
    assert GLASS_IMPROVEMENT_THRESHOLDS["bucket_overlap"] == 0.05
    assert GLASS_IMPROVEMENT_THRESHOLDS["bucket_count_proximity"] == 0.20


def test_run_local_profile_capture_passes_legacy_surface(monkeypatch, tmp_path: Path):
    import scripts.run_glass_calibration as module

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"providers": {"rektslug": {}}}), encoding="utf-8")
    commands: list[list[str]] = []

    def _fake_run(cmd, capture_output, text, timeout):
        commands.append(cmd)

        class _Result:
            stdout = f"comparison report: {report_path}\n"
            stderr = ""

        return _Result()

    monkeypatch.setattr(module, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    resolved = run_local_profile_capture("BTC", "1w", "rektslug-glass", attempts=1)

    assert resolved == report_path
    assert "--surface" in commands[0]
    assert commands[0][commands[0].index("--surface") + 1] == "legacy"
