from scripts.sweep_hl_reserved_margin_guardrail import _rank_threshold_results


def test_rank_threshold_results_prefers_cross_margin_gain_then_lower_error():
    ranked = _rank_threshold_results(
        [
            {
                "threshold": 0.01,
                "all_accounts": {
                    "improvement_rate": 0.55,
                },
                "cross_margin_only": {
                    "improvement_rate": 0.70,
                    "improved_positions": 70,
                    "worsened_positions": 30,
                    "v1_1_mean_abs_error": 100.0,
                },
            },
            {
                "threshold": 0.02,
                "all_accounts": {
                    "improvement_rate": 0.50,
                },
                "cross_margin_only": {
                    "improvement_rate": 0.70,
                    "improved_positions": 70,
                    "worsened_positions": 30,
                    "v1_1_mean_abs_error": 90.0,
                },
            },
            {
                "threshold": 0.05,
                "all_accounts": {
                    "improvement_rate": 0.90,
                },
                "cross_margin_only": {
                    "improvement_rate": 0.60,
                    "improved_positions": 90,
                    "worsened_positions": 10,
                    "v1_1_mean_abs_error": 50.0,
                },
            },
        ]
    )

    assert [row["threshold"] for row in ranked] == [0.02, 0.01, 0.05]
