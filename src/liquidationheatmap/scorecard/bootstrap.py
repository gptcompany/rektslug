"""Bootstrap dominance primitives for scorecard logic.

Functions in this module provide pairwise expert dominance comparisons using
bootstrap confidence intervals.
"""

import random
from typing import Any, Callable

from src.liquidationheatmap.models.scorecard import BootstrapDominanceResult


def bootstrap_dominance(
    obs_a: list[Any],
    obs_b: list[Any],
    metric_fn: Callable[[list[Any]], float],
    expert_a: str,
    expert_b: str,
    metric_name: str,
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> BootstrapDominanceResult:
    """Compute probabilistic dominance using bootstrap CI.

    Resamples both observation sets with replacement n_bootstrap times to find
    the probability that expert_a outperforms expert_b. The confidence interval
    is derived from the distribution of the binary comparison outcomes.
    """
    if not obs_a or not obs_b:
        return BootstrapDominanceResult(
            expert_a=expert_a,
            expert_b=expert_b,
            metric=metric_name,
            p_a_better=0.5,
            significant=False,
            ci_lower=0.5,
            ci_upper=0.5,
            n_bootstrap=n_bootstrap,
        )

    rng = random.Random(seed)
    outcomes = []

    n_a = len(obs_a)
    n_b = len(obs_b)

    for _ in range(n_bootstrap):
        # Primary bootstrap: resample original observations
        sample_a = [rng.choice(obs_a) for _ in range(n_a)]
        sample_b = [rng.choice(obs_b) for _ in range(n_b)]

        m_a = metric_fn(sample_a)
        m_b = metric_fn(sample_b)

        if m_a > m_b:
            outcomes.append(1.0)
        elif m_a < m_b:
            outcomes.append(0.0)
        else:
            outcomes.append(0.5)

    p_a_better = sum(outcomes) / n_bootstrap

    # Derive CI from the outcomes.
    # For indicator variables, the quantiles will be 0, 0.5 or 1.
    # Significant if the 95% CI (e.g. [2.5th, 97.5th] percentiles) excludes 0.5.
    # This happens if p_a_better > 0.975 (CI=[1,1]) or p_a_better < 0.025 (CI=[0,0]).
    outcomes.sort()
    ci_lower = outcomes[int(n_bootstrap * 0.025)]
    ci_upper = outcomes[int(n_bootstrap * 0.975)]

    # Standard dominance significance: does the CI exclude 0.5?
    # Note: ci_lower > 0.5 implies A is strictly better in > 97.5% of cases.
    # ci_upper < 0.5 implies B is strictly better in > 97.5% of cases.
    significant = (ci_lower > 0.5) or (ci_upper < 0.5)

    return BootstrapDominanceResult(
        expert_a=expert_a,
        expert_b=expert_b,
        metric=metric_name,
        p_a_better=p_a_better,
        significant=significant,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        n_bootstrap=n_bootstrap,
    )
