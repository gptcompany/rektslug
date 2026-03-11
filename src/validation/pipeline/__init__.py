"""Validation pipeline module for automated model validation.

This module provides:
- ValidationPipelineRun: Track pipeline execution state
- PipelineOrchestrator: Coordinate validation types
- MetricsAggregator: Combine metrics for dashboard
- CIRunner: GitHub Actions entry point
"""

from src.validation.pipeline.metrics_aggregator import (
    MetricsAggregator,
    get_dashboard_metrics,
)
from src.validation.pipeline.models import (
    Alert,
    BacktestResultSummary,
    DashboardMetrics,
    GateDecision,
    PipelineStatus,
    TrendDataPoint,
    TriggerType,
    ValidationPipelineRun,
    ValidationType,
    compute_overall_grade,
    compute_overall_score,
    determine_dashboard_status,
    evaluate_gate_2,
)
from src.validation.pipeline.orchestrator import (
    PipelineConfig,
    PipelineOrchestrator,
    run_pipeline,
)

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
