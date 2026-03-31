"""Tests for the reserved margin validation CLI helpers."""

import json

from scripts.validate_reserved_margin import (
    DEFAULT_MODE_SCAN_OUTPUT,
    _build_mode_detection_payload,
    _load_orders_by_user,
    _load_users,
    _resolve_existing_data_file,
    _resolve_mode_scan_users,
    _resolve_output_path,
    _serialize_report,
)
from src.liquidationheatmap.hyperliquid.models import (
    LiqPxComparisonSummary,
    MarginModeReportSummary,
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


def test_load_users_reads_ranked_user_lists(tmp_path):
    path = tmp_path / "proxy_summary.json"
    path.write_text(
        json.dumps(
            {
                "top_users_by_exposure_increasing_lower_bound": [
                    {"user": "0xabc", "value": 10},
                    {"user": "0xdef", "value": 9},
                ],
                "top_users_by_abs_margin_gap": [
                    {"user": "0xdef", "value": 8},
                    {"user": "0x123", "value": 7},
                ],
            }
        ),
        encoding="utf-8",
    )

    users = _load_users([], str(path))

    assert users == ["0xabc", "0xdef", "0x123"]


def test_serialize_report_adds_summary_fields():
    report = MarginValidationReport(
        timestamp="2026-03-31T00:00:00+00:00",
        users_analyzed=1,
        tolerance_rate=1.0,
        mean_mmr_deviation_pct=0.5,
        margin_mode_distribution={"cross_margin": 1},
        mode_summaries={
            "cross_margin": MarginModeReportSummary(
                users_analyzed=1,
                tolerance_rate=1.0,
                mean_mmr_deviation_pct=0.5,
                liq_px_summary=None,
            )
        },
        results=[
            MarginValidationResult(
                user="0xabc",
                mode=MarginMode.CROSS_MARGIN,
                account_abstraction="default",
                api_total_margin_used=10.0,
                api_cross_maintenance_margin_used=5.0,
                sidecar_total_mmr=5.0,
                deviation_mmr_pct=0.5,
                positions=[],
                factors=[],
            )
        ],
        liq_px_summary=LiqPxComparisonSummary(
            positions_compared=1,
            improved_positions=1,
            worsened_positions=0,
            unchanged_positions=0,
            v1_mean_abs_error=10.0,
            v1_1_mean_abs_error=5.0,
            improvement_rate=1.0,
        ),
    )

    payload = _serialize_report(report)

    assert payload["passed"] is True
    assert payload["passed_all_accounts"] is True
    assert payload["passed_cross_margin_only"] is True
    assert payload["user_count"] == 1
    assert payload["results"][0]["mode"] == "cross_margin"
    assert payload["liq_px_summary"]["improved_positions"] == 1


def test_serialize_report_marks_cross_only_failure_without_cross_summary():
    report = MarginValidationReport(
        timestamp="2026-03-31T00:00:00+00:00",
        users_analyzed=1,
        tolerance_rate=0.95,
        mean_mmr_deviation_pct=0.5,
        margin_mode_distribution={"isolated_margin": 1},
        mode_summaries={},
        results=[
            MarginValidationResult(
                user="0xabc",
                mode=MarginMode.ISOLATED_MARGIN,
                account_abstraction="default",
                api_total_margin_used=10.0,
                api_cross_maintenance_margin_used=5.0,
                sidecar_total_mmr=5.0,
                deviation_mmr_pct=0.5,
                positions=[],
                factors=[],
            )
        ],
        liq_px_summary=None,
    )

    payload = _serialize_report(report)

    assert payload["passed"] is True
    assert payload["passed_all_accounts"] is True
    assert payload["passed_cross_margin_only"] is False


def test_load_orders_by_user_reads_nested_orders(tmp_path):
    path = tmp_path / "outliers_with_orders.json"
    path.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "user": "0xabc",
                        "orders": [
                            {
                                "oid": 1,
                                "coin": "ETH",
                                "side": "B",
                                "size": 1.0,
                                "orig_size": 1.0,
                                "limit_px": 2000.0,
                                "reduce_only": False,
                                "is_trigger": False,
                                "is_position_tpsl": False,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    orders_by_user = _load_orders_by_user(str(path))

    assert list(orders_by_user) == ["0xabc"]
    assert orders_by_user["0xabc"][0].coin == "ETH"
    assert orders_by_user["0xabc"][0].limit_px == 2000.0


def test_resolve_mode_scan_users_uses_default_sources(monkeypatch, tmp_path):
    proxy_path = tmp_path / "proxy.json"
    proxy_path.write_text(
        json.dumps(
            {
                "top_users_by_exposure_increasing_lower_bound": [
                    {"user": "0xabc"},
                    {"user": "0xdef"},
                ]
            }
        ),
        encoding="utf-8",
    )
    outliers_path = tmp_path / "outliers.json"
    outliers_path.write_text(
        json.dumps(
            {
                "users": [
                    {"user": "0xdef"},
                    {"user": "0x123"},
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.validate_reserved_margin.DEFAULT_MODE_SCAN_FILES",
        [str(proxy_path), str(outliers_path)],
    )

    users, sources = _resolve_mode_scan_users(None, None, limit=50)

    assert users == ["0xabc", "0xdef", "0x123"]
    assert sources == [str(proxy_path), str(outliers_path)]


def test_resolve_mode_scan_users_full_population_uses_proxy_loader(monkeypatch):
    monkeypatch.setattr(
        "scripts.validate_reserved_margin._load_full_population_from_proxy_report",
        lambda path: ["0xaaa", "0xbbb"],
    )

    users, sources = _resolve_mode_scan_users(
        None,
        None,
        full_population=True,
        limit=50,
    )

    assert users == ["0xaaa", "0xbbb"]
    assert sources == [
        "data/validation/hl_reserved_margin_proxy_eth_sample.json",
        "full_population",
    ]


def test_resolve_existing_data_file_falls_back_to_single_zst(tmp_path):
    hour_dir = tmp_path / "hourly" / "20260321"
    hour_dir.mkdir(parents=True)
    actual_file = hour_dir / "23.zst"
    actual_file.write_bytes(b"test")

    resolved = _resolve_existing_data_file(str(hour_dir / "2.zst"))

    assert resolved == actual_file


def test_resolve_output_path_switches_default_for_detect_modes():
    assert (
        _resolve_output_path("validation_report.json", detect_modes=True)
        == DEFAULT_MODE_SCAN_OUTPUT
    )
    assert (
        _resolve_output_path("custom.json", detect_modes=True)
        == "custom.json"
    )


def test_build_mode_detection_payload_collects_portfolio_accounts():
    payload = _build_mode_detection_payload(
        [
            {
                "user": "0xabc",
                "user_abstraction": "portfolioMargin",
                "mode": "portfolio_margin",
                "portfolio_margin_ratio": 0.91,
                "account_value": 123.0,
                "position_count": 2,
            },
            {"user": "0xdef", "user_abstraction": "default", "mode": "cross_margin"},
            {"user": "0xghi", "mode": None, "error": "timeout"},
        ],
        scanned_users=["0xabc", "0xdef", "0xghi"],
        sources=["proxy.json"],
        limit=50,
    )

    assert payload["scan_limit"] == 50
    assert payload["population_sources"] == ["proxy.json"]
    assert payload["users_requested"] == 3
    assert payload["users_succeeded"] == 2
    assert payload["users_failed"] == 1
    assert payload["mode_counts"]["portfolio_margin"] == 1
    assert payload["account_abstraction_counts"] == {
        "portfolioMargin": 1,
        "default": 1,
    }
    assert payload["portfolio_margin_accounts"] == [
        {
            "user": "0xabc",
            "user_abstraction": "portfolioMargin",
            "portfolio_margin_ratio": 0.91,
            "account_value": 123.0,
            "position_count": 2,
        }
    ]
