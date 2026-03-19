"""Validation pipeline module for automated model validation.

This module provides:
- ValidationPipelineRun: Track pipeline execution state
- PipelineOrchestrator: Coordinate validation types
- MetricsAggregator: Combine metrics for dashboard
- CIRunner: GitHub Actions entry point
"""

from __future__ import annotations

from importlib import import_module

_MISSING_EXPORT_ERRORS: dict[str, ImportError] = {}


def _load_exports(module_name: str, export_names: tuple[str, ...]) -> None:
    """Load public exports while keeping missing optional dependencies explicit."""

    try:
        module = import_module(module_name)
    except ImportError as exc:
        for export_name in export_names:
            _MISSING_EXPORT_ERRORS[export_name] = exc
        return

    for export_name in export_names:
        globals()[export_name] = getattr(module, export_name)


_load_exports(
    "src.validation.pipeline.metrics_aggregator",
    ("MetricsAggregator", "get_dashboard_metrics"),
)
_load_exports(
    "src.validation.pipeline.models",
    (
        "Alert",
        "BacktestResultSummary",
        "DashboardMetrics",
        "GateDecision",
        "PipelineStatus",
        "TrendDataPoint",
        "TriggerType",
        "ValidationPipelineRun",
        "ValidationType",
        "compute_overall_grade",
        "compute_overall_score",
        "determine_dashboard_status",
        "evaluate_gate_2",
    ),
)
_load_exports(
    "src.validation.pipeline.orchestrator",
    ("PipelineConfig", "PipelineOrchestrator", "run_pipeline"),
)


def __getattr__(name: str):
    if name in _MISSING_EXPORT_ERRORS:
        exc = _MISSING_EXPORT_ERRORS[name]
        raise ImportError(
            f"{name} is unavailable because a validation pipeline dependency failed to import: {exc}"
        ) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Models
    "ValidationPipelineRun",
    "PipelineStatus",
    "ValidationType",
    "GateDecision",
    "TriggerType",
    "DashboardMetrics",
    "BacktestResultSummary",
    "TrendDataPoint",
    "Alert",
    # Functions
    "evaluate_gate_2",
    "compute_overall_grade",
    "compute_overall_score",
    "determine_dashboard_status",
    # Orchestrator
    "PipelineConfig",
    "PipelineOrchestrator",
    "run_pipeline",
    # Aggregator
    "MetricsAggregator",
    "get_dashboard_metrics",
]
