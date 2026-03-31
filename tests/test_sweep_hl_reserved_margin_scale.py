from scripts.sweep_hl_reserved_margin_scale import _rank_scale_results


def test_rank_scale_results_prefers_cross_margin_improvement_then_fewer_regressions():
    ranked = _rank_scale_results(
        [
            {
                "scale": 0.5,
                "all_accounts": {
                    "improvement_rate": 0.55,
                },
                "cross_margin_only": {
                    "improvement_rate": 0.70,
                    "improved_positions": 70,
                    "worsened_positions": 30,
                },
            },
            {
                "scale": 0.75,
                "all_accounts": {
                    "improvement_rate": 0.40,
                },
                "cross_margin_only": {
                    "improvement_rate": 0.70,
                    "improved_positions": 70,
                    "worsened_positions": 20,
                },
            },
            {
                "scale": 1.0,
                "all_accounts": {
                    "improvement_rate": 0.80,
                },
                "cross_margin_only": {
                    "improvement_rate": 0.60,
                    "improved_positions": 90,
                    "worsened_positions": 10,
                },
            },
        ]
    )

    assert [row["scale"] for row in ranked] == [0.75, 0.5, 1.0]
