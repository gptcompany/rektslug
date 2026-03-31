from scripts.compare_hl_reserved_margin_netting_modes import _rank_netting_results


def test_rank_netting_results_prefers_cross_margin_improvement_then_lower_error():
    ranked = _rank_netting_results(
        [
            {
                "netting_mode": "per_order_mmr",
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
                "netting_mode": "net_delta_mmr",
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
                "netting_mode": "side_max_per_order_mmr",
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

    assert [row["netting_mode"] for row in ranked] == [
        "net_delta_mmr",
        "per_order_mmr",
        "side_max_per_order_mmr",
    ]
