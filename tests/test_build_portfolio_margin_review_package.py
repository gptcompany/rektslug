import json
from pathlib import Path

from scripts.build_portfolio_margin_review_package import build_review_package


def test_build_review_package_summarizes_fixture_accounts(tmp_path):
    fixture_path = Path("tests/fixtures/hyperliquid/portfolio_margin_live_cases.json")

    accounts_payload = {
        "portfolio_margin_accounts": [
            {"user": "0xb1c4a17f0f39c2b04333831104a82e94ab808510"},
            {"user": "0xdc00aede8219c1151ddd86372deed7a36bdeb405"},
            {"user": "0xfc8b2f2b98705037ec9fa816f40c42077b237d3c"},
        ]
    }
    repo_scan_payload = {
        "results": [
            {"user": "0xb1c4a17f0f39c2b04333831104a82e94ab808510", "mode": "portfolio_margin"},
            {"user": "0xdc00aede8219c1151ddd86372deed7a36bdeb405", "mode": "portfolio_margin"},
            {"user": "0xfc8b2f2b98705037ec9fa816f40c42077b237d3c", "mode": "portfolio_margin"},
        ]
    }

    accounts_path = tmp_path / "accounts.json"
    accounts_path.write_text(json.dumps(accounts_payload), encoding="utf-8")
    repo_scan_path = tmp_path / "repo_scan.json"
    repo_scan_path.write_text(json.dumps(repo_scan_payload), encoding="utf-8")

    payload = build_review_package(fixture_path, accounts_path, repo_scan_path)

    assert payload["fixture_user_count"] == 3
    assert payload["observed_portfolio_margin_account_count"] == 3
    assert payload["repo_scan_result_count"] == 3
    assert payload["comparable_position_count"] == 1
    assert payload["within_tolerance_count"] == 1
    assert payload["within_tolerance_rate"] == 1.0
    assert len(payload["cases"]) == 3
    assert any(case["positions"][0]["comparable"] for case in payload["cases"] if case["positions"])
    assert "currently observable PM universe" in payload["residual_note"]
