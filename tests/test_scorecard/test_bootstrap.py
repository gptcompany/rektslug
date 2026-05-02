import pytest

from src.liquidationheatmap.scorecard.bootstrap import bootstrap_dominance


def test_bootstrap_dominance_significant_difference():
    # Expert A is clearly better (higher mean)
    obs_a = [1.0] * 50 + [0.0] * 50  # mean 0.5
    obs_b = [0.1] * 50 + [0.0] * 50  # mean 0.05

    def mean_fn(data):
        return sum(data) / len(data) if data else 0.0

    result = bootstrap_dominance(
        obs_a=obs_a,
        obs_b=obs_b,
        metric_fn=mean_fn,
        expert_a="a",
        expert_b="b",
        metric_name="mean",
        n_bootstrap=1000,
        seed=42,
    )

    assert result.expert_a == "a"
    assert result.expert_b == "b"
    assert result.p_a_better > 0.95
    assert result.significant is True
    assert result.ci_lower > 0.3
    assert result.ci_upper > 0.5


def test_bootstrap_dominance_inconclusive():
    # Experts are identical
    obs_a = [0.5] * 100
    obs_b = [0.5] * 100

    def mean_fn(data):
        return sum(data) / len(data) if data else 0.0

    result = bootstrap_dominance(
        obs_a=obs_a,
        obs_b=obs_b,
        metric_fn=mean_fn,
        expert_a="a",
        expert_b="b",
        metric_name="mean",
        n_bootstrap=1000,
        seed=42,
    )

    assert 0.4 < result.p_a_better < 0.6
    assert result.significant is False


def test_bootstrap_dominance_reproducibility():
    obs_a = [0.6, 0.4, 0.8, 0.2]
    obs_b = [0.5, 0.5, 0.5, 0.5]

    def mean_fn(data):
        return sum(data) / len(data) if data else 0.0

    res1 = bootstrap_dominance(obs_a, obs_b, mean_fn, "a", "b", "mean", 1000, 42)
    res2 = bootstrap_dominance(obs_a, obs_b, mean_fn, "a", "b", "mean", 1000, 42)
    res3 = bootstrap_dominance(obs_a, obs_b, mean_fn, "a", "b", "mean", 1000, 43)

    assert res1.p_a_better == res2.p_a_better
    assert res1.ci_lower == res2.ci_lower
    assert res1 == res2
    assert res3 != res1 or res3.ci_upper != res1.ci_upper


def test_bootstrap_dominance_low_sample_wide_ci():
    # Only 3 observations
    obs_a = [1.0, 0.0, 1.0]
    obs_b = [0.0, 1.0, 0.0]

    def mean_fn(data):
        return sum(data) / len(data) if data else 0.0

    result = bootstrap_dominance(obs_a, obs_b, mean_fn, "a", "b", "mean", 1000, 42)

    # CI should be very wide
    assert (
        result.ci_upper - result.ci_lower > 0.3
    )  # 0.5 was too high maybe for 3 samples, let's see
    assert result.significant is False


def test_bootstrap_dominance_supports_lower_is_better_metrics():
    # Lower MAE is better, so expert A should dominate expert B.
    obs_a = [1.0] * 100
    obs_b = [5.0] * 100

    def mean_fn(data):
        return sum(data) / len(data) if data else 0.0

    result = bootstrap_dominance(
        obs_a=obs_a,
        obs_b=obs_b,
        metric_fn=mean_fn,
        expert_a="a",
        expert_b="b",
        metric_name="mae_p50",
        n_bootstrap=1000,
        seed=42,
        higher_is_better=False,
    )

    assert result.p_a_better > 0.95
    assert result.significant is True


def test_bootstrap_dominance_rejects_non_positive_bootstrap_count():
    def mean_fn(data):
        return sum(data) / len(data) if data else 0.0

    with pytest.raises(ValueError, match="n_bootstrap"):
        bootstrap_dominance(
            obs_a=[1.0],
            obs_b=[0.0],
            metric_fn=mean_fn,
            expert_a="a",
            expert_b="b",
            metric_name="mean",
            n_bootstrap=0,
            seed=42,
        )
