from scripts.compare_hl_reserved_margin_allocation_modes import _summarize_errors


def test_summarize_errors_counts_improved_worsened_and_unchanged():
    summary = _summarize_errors(
        [10.0, 5.0, 4.0, 3.0],
        [8.0, 7.0, 4.0, 1.0],
        "target_coin_only",
    )

    assert summary.mode == "target_coin_only"
    assert summary.positions_compared == 4
    assert summary.improved_positions == 2
    assert summary.worsened_positions == 1
    assert summary.unchanged_positions == 1
    assert summary.improvement_rate == 0.5
    assert summary.v1_mean_abs_error == 5.5
    assert summary.v1_1_mean_abs_error == 5.0
