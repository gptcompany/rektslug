"""Bootstrap dominance primitives for scorecard logic.

Functions in this module provide pairwise expert dominance comparisons using
bootstrap confidence intervals.
"""

from typing import Any, Callable, List

from src.liquidationheatmap.models.scorecard import BootstrapDominanceResult


def bootstrap_dominance(
    obs_a: List[Any],
    obs_b: List[Any],
    metric_fn: Callable[[List[Any]], float],
    n_bootstrap: int,
    seed: int,
) -> BootstrapDominanceResult:
    """Compute probabilistic dominance using bootstrap CI."""
    raise NotImplementedError
