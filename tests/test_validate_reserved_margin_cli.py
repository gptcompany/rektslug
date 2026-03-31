"""Tests for the reserved margin validation CLI helpers."""

import json

from scripts.validate_reserved_margin import _load_users, _serialize_report
from src.liquidationheatmap.hyperliquid.models import (
    MarginMode,
    MarginValidationReport,
    MarginValidationResult,
)


def test_load_users_reads_top_level_addresses(tmp_path):
    path = tmp_path / "outliers.json"
    path.write_text(
        json.dumps(
            {
                "0xabc": {"delta": 1},
                "0xdef": {"delta": 2},
                "note": "ignore",
            }
        ),
        encoding="utf-8",
    )

    users = _load_users([], str(path))

    assert users == ["0xabc", "0xdef"]


def test_load_users_reads_nested_user_entries(tmp_path):
    path = tmp_path / "outliers_nested.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"selected_user_count": 2},
                "users": [
                    {"user": "0xabc", "report_row": {}},
                    {"user": "0xdef", "report_row": {}},
                ],
            }
        ),
        encoding="utf-8",
    )

    users = _load_users([], str(path))

    assert users == ["0xabc", "0xdef"]


def test_serialize_report_adds_summary_fields():
    report = MarginValidationReport(
        timestamp="2026-03-31T00:00:00+00:00",
        users_analyzed=1,
        tolerance_rate=1.0,
        mean_mmr_deviation_pct=0.5,
        margin_mode_distribution={"cross_margin": 1},
        results=[
            MarginValidationResult(
                user="0xabc",
                mode=MarginMode.CROSS_MARGIN,
                api_total_margin_used=10.0,
                api_cross_maintenance_margin_used=5.0,
                sidecar_total_mmr=5.0,
                deviation_mmr_pct=0.5,
                positions=[],
                factors=[],
            )
        ],
    )

    payload = _serialize_report(report)

    assert payload["passed"] is True
    assert payload["user_count"] == 1
    assert payload["results"][0]["mode"] == "cross_margin"
