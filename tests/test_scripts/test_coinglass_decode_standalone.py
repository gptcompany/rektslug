"""Regression tests for scripts/coinglass_decode_standalone.js."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "coinglass_decode_standalone.js"


def _run_decoder_helper(summary: dict) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node is not installed")

    script_path = json.dumps(str(SCRIPT_PATH))
    summary_json = json.dumps(summary)
    expression = f"""
const decoder = require({script_path});
const summary = {summary_json};
const capture = decoder.selectSummaryCapture(summary);
console.log(JSON.stringify({{
  saved_file: capture ? capture.saved_file : null,
  time: capture ? decoder.resolveCaptureTime(capture) : null
}}));
"""
    result = subprocess.run(
        ["node", "-e", expression],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_select_summary_capture_prefers_liqmap_endpoint() -> None:
    summary = {
        "captures": [
            {
                "source_url": "https://capi.coinglass.com/api/strapi/page?slug=liquidations&lang=en",
                "response_headers": {"content-type": "application/json"},
                "saved_file": "01_page.json",
            },
            {
                "source_url": "https://capi.coinglass.com/api/index/5/liqMap?symbol=Binance_BTCUSDT",
                "response_headers": {
                    "encryption": "true",
                    "user": "encrypted-user-header",
                    "time": "1773948212605",
                },
                "saved_file": "02_liqmap.json",
            },
        ]
    }

    result = _run_decoder_helper(summary)

    assert result == {
        "saved_file": "02_liqmap.json",
        "time": "1773948212605",
    }


def test_resolve_capture_time_falls_back_to_cache_ts_v2() -> None:
    summary = {
        "captures": [
            {
                "source_url": "https://capi.coinglass.com/api/index/5/liqMap?symbol=Binance_BTCUSDT",
                "response_headers": {
                    "encryption": "true",
                    "user": "encrypted-user-header",
                },
                "request_headers": {"cache-ts-v2": "1772541217178"},
                "saved_file": "03_liqmap.json",
            }
        ]
    }

    result = _run_decoder_helper(summary)

    assert result == {
        "saved_file": "03_liqmap.json",
        "time": "1772541217178",
    }
