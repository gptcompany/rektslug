from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from scripts.run_visual_harness import main, parse_args


def test_parse_args_accepts_timeframe():
    with patch(
        "sys.argv",
        [
            "run_visual_harness.py",
            "--timeframe",
            "1d",
        ],
    ):
        args = parse_args()

    assert args.product == "liq-map"
    assert args.renderer == "plotly"
    assert args.provider == "coinank"
    assert args.symbol == "BTCUSDT"
    assert args.exchange == "binance"
    assert args.timeframe == "1d"
    assert args.window is None


def test_parse_args_accepts_window_for_heat_map_and_lightweight():
    with patch(
        "sys.argv",
        [
            "run_visual_harness.py",
            "--product",
            "liq-heat-map",
            "--renderer",
            "lightweight",
            "--window",
            "48h",
        ],
    ):
        args = parse_args()

    assert args.product == "liq-heat-map"
    assert args.renderer == "lightweight"
    assert args.timeframe is None
    assert args.window == "48h"


def test_main_prints_manifest_and_score_paths(capsys, tmp_path: Path):
    class _Outcome:
        exit_code = 0
        manifest_path = tmp_path / "manifest.json"
        score_path = tmp_path / "score.json"

    with patch(
        "sys.argv",
        [
            "run_visual_harness.py",
            "--run-id",
            "run-001",
            "--timeframe",
            "1d",
            "--output-dir",
            str(tmp_path),
        ],
    ), patch("scripts.run_visual_harness.run_visual_pair", return_value=_Outcome()) as mock_run:
        exit_code = main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "manifest=" in output
    assert "score=" in output
    assert mock_run.called


def test_main_returns_non_zero_and_prints_manifest_for_unwired_lightweight_path(
    capsys,
    tmp_path: Path,
):
    with patch(
        "sys.argv",
        [
            "run_visual_harness.py",
            "--run-id",
            "run-heat-window",
            "--provider",
            "bitcoincounterflow",
            "--product",
            "liq-heat-map",
            "--renderer",
            "lightweight",
            "--window",
            "48h",
            "--output-dir",
            str(tmp_path),
        ],
    ):
        exit_code = main()

    output = capsys.readouterr().out
    manifest_path = (
        tmp_path
        / "run-heat-window"
        / "run-heat-window_bitcoincounterflow_liq-heat-map_lightweight_btcusdt_48h_manifest.json"
    )

    assert exit_code == 1
    assert f"manifest={manifest_path}" in output
    assert "score=" not in output
    assert manifest_path.exists()


def test_script_executes_as_file_without_src_import_error():
    repo_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "run_visual_harness.py"), "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "ModuleNotFoundError" not in result.stderr
    assert "No module named 'src'" not in result.stderr
