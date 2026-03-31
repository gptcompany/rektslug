"""Tests for Hyperliquid validation blocker summary script."""

from scripts.summarize_hl_validation_blockers import build_blocker_summary


def test_build_blocker_summary_prioritizes_cross_margin_and_sorts_by_deviation():
    report = {
        "timestamp": "2026-03-31T00:00:00+00:00",
        "users_analyzed": 3,
        "tolerance_rate": 0.5,
        "passed_all_accounts": False,
        "passed_cross_margin_only": False,
        "margin_mode_distribution": {"cross_margin": 2, "isolated_margin": 1},
        "mode_summaries": {
            "cross_margin": {
                "tolerance_rate": 0.5,
                "mean_mmr_deviation_pct": 12.0,
            }
        },
        "results": [
            {
                "user": "0xlow",
                "mode": "cross_margin",
                "deviation_mmr_pct": 2.0,
                "api_cross_maintenance_margin_used": 100.0,
                "sidecar_total_mmr": 102.0,
                "liq_px_summary": {
                    "positions_compared": 2,
                    "improved_positions": 2,
                    "worsened_positions": 0,
                    "improvement_rate": 1.0,
                },
            },
            {
                "user": "0xhigh",
                "mode": "cross_margin",
                "deviation_mmr_pct": 25.0,
                "api_cross_maintenance_margin_used": 100.0,
                "sidecar_total_mmr": 125.0,
                "liq_px_summary": {
                    "positions_compared": 1,
                    "improved_positions": 0,
                    "worsened_positions": 1,
                    "improvement_rate": 0.0,
                },
            },
            {
                "user": "0xiso",
                "mode": "isolated_margin",
                "deviation_mmr_pct": 50.0,
                "api_cross_maintenance_margin_used": 100.0,
                "sidecar_total_mmr": 150.0,
            },
        ],
    }
    outliers = {
        "users": [
            {
                "user": "0xhigh",
                "report_row": {
                    "position_count": 3,
                    "active_order_count": 2,
                    "non_reduce_only_order_count": 1,
                    "solver_mmr_total": 90.0,
                    "margin_gap_total": -10.0,
                },
                "positions": [
                    {"coin": "BTC", "size": 2.0, "mark_px": 100.0, "entry_px": 95.0, "maintenance_margin": 10.0, "margin": 20.0},
                    {"coin": "ETH", "size": 5.0, "mark_px": 10.0, "entry_px": 11.0, "maintenance_margin": 3.0, "margin": 4.0},
                ],
                "orders": [{}, {}],
            },
            {
                "user": "0xlow",
                "report_row": {
                    "position_count": 1,
                    "active_order_count": 0,
                    "solver_mmr_total": 95.0,
                    "margin_gap_total": -5.0,
                },
                "positions": [
                    {"coin": "SOL", "size": 1.0, "mark_px": 50.0, "entry_px": 51.0, "maintenance_margin": 1.0, "margin": 2.0},
                ],
                "orders": [],
            },
        ]
    }

    summary = build_blocker_summary(report, outliers, top_n=2, positions_per_user=1)

    assert summary["summary"]["cross_margin_users"] == 2
    assert summary["summary"]["cross_margin_tolerance_rate"] == 0.5
    assert [item["user"] for item in summary["cross_margin_blockers"]] == ["0xhigh", "0xlow"]
    assert summary["cross_margin_blockers"][0]["mmr_gap_usd"] == 25.0
    assert summary["cross_margin_blockers"][0]["top_positions"][0]["coin"] == "BTC"
    assert summary["cross_margin_blockers"][0]["top_positions"][0]["estimated_notional_usd"] == 200.0


def test_build_blocker_summary_handles_missing_sample_user():
    report = {
        "timestamp": "2026-03-31T00:00:00+00:00",
        "users_analyzed": 1,
        "tolerance_rate": 0.0,
        "passed_all_accounts": False,
        "passed_cross_margin_only": False,
        "margin_mode_distribution": {"cross_margin": 1},
        "mode_summaries": {"cross_margin": {"tolerance_rate": 0.0, "mean_mmr_deviation_pct": 40.0}},
        "results": [
            {
                "user": "0xmissing",
                "mode": "cross_margin",
                "deviation_mmr_pct": 40.0,
                "api_cross_maintenance_margin_used": 10.0,
                "sidecar_total_mmr": 14.0,
            }
        ],
    }

    summary = build_blocker_summary(report, {"users": []}, top_n=1, positions_per_user=2)

    blocker = summary["cross_margin_blockers"][0]
    assert blocker["user"] == "0xmissing"
    assert blocker["position_count"] == 0
    assert blocker["active_order_count"] == 0
    assert blocker["top_positions"] == []
