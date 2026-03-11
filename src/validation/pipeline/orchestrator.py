"""Pipeline orchestrator for coordinating validation runs.

Orchestrates backtest validation and optional Coinglass comparison,
implementing Gate 2 decision logic per specs/014-validation-pipeline/plan.md.
"""

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from src.liquidationheatmap.validation.backtest import (
    BacktestConfig,
    BacktestResult,
    run_backtest,
)
from src.validation.pipeline.models import (
    BacktestResultSummary,
    GateDecision,
    PipelineStatus,
    TriggerType,
    ValidationPipelineRun,
    ValidationType,
    compute_overall_grade,
    compute_overall_score,
    evaluate_gate_2,
)


class PipelineConfig:
    """Configuration object for a validation pipeline run."""

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        validation_types: Optional[list[ValidationType]] = None,
        trigger_type: TriggerType = TriggerType.MANUAL,
        triggered_by: str = "system",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        tolerance_pct: float = 2.0,
        prediction_horizon_minutes: int = 60,
        verbose: bool = False,
    ):
        self.symbol = symbol
        self.validation_types = validation_types or [ValidationType.BACKTEST]
        self.trigger_type = trigger_type
        self.triggered_by = triggered_by
        self.start_date = start_date
        self.end_date = end_date
        self.tolerance_pct = tolerance_pct
        self.prediction_horizon_minutes = prediction_horizon_minutes
        self.verbose = verbose


class PipelineOrchestrator:
    """Coordinates validation pipeline execution.

    Responsibilities:
    - Run backtest validation
    - Evaluate Gate 2 decision
    - Optionally run Coinglass comparison
    - Aggregate results into ValidationPipelineRun
    """

    def __init__(
        self,
        db_path: str = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
        reports_dir: str = "reports",
        backtest_runner: Callable[[BacktestConfig, bool], BacktestResult] = run_backtest,
    ):
        """Initialize orchestrator.

        Args:
            db_path: Path to DuckDB database
            reports_dir: Directory for output reports
        """
        self.db_path = db_path
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.backtest_runner = backtest_runner

    def run_pipeline(
        self,
        config: PipelineConfig | str | None = None,
        *,
        symbol: str = "BTCUSDT",
        validation_types: list[ValidationType] | None = None,
        trigger_type: TriggerType = TriggerType.MANUAL,
        triggered_by: str = "system",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        tolerance_pct: float = 2.0,
        prediction_horizon_minutes: int = 60,
        verbose: bool = False,
    ) -> ValidationPipelineRun:
        """Run the validation pipeline.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            validation_types: Types of validation to run (default: [BACKTEST])
            trigger_type: How pipeline was triggered
            triggered_by: User or system identifier
            start_date: Backtest start date (default: 30 days ago)
            end_date: Backtest end date (default: yesterday)
            tolerance_pct: Price tolerance for matching
            prediction_horizon_minutes: Prediction lookahead window
            verbose: Print progress messages

        Returns:
            ValidationPipelineRun with results and gate decisions
        """
        if isinstance(config, PipelineConfig):
            pipeline_config = config
        else:
            if isinstance(config, str):
                symbol = config
            pipeline_config = PipelineConfig(
                symbol=symbol,
                validation_types=validation_types,
                trigger_type=trigger_type,
                triggered_by=triggered_by,
                start_date=start_date,
                end_date=end_date,
                tolerance_pct=tolerance_pct,
                prediction_horizon_minutes=prediction_horizon_minutes,
                verbose=verbose,
            )

        # Generate run ID
        run_id = str(uuid.uuid4())
        started_at = datetime.now()

        # Initialize pipeline run
        pipeline_run = self._initialize_run(run_id, started_at, pipeline_config)

        if pipeline_config.verbose:
            print(f"🚀 Starting validation pipeline: {run_id}")
            print(f"   Symbol: {pipeline_config.symbol}")
            print(f"   Validation types: {[vt.value for vt in pipeline_config.validation_types]}")

        try:
            # Run backtest if requested
            if self._should_run(ValidationType.BACKTEST, pipeline_config.validation_types):
                self._execute_backtest_step(pipeline_run, pipeline_config)

            # Run Coinglass comparison if requested (informational only)
            if self._should_run(ValidationType.COINGLASS, pipeline_config.validation_types):
                if pipeline_config.verbose:
                    print("\n📊 Coinglass comparison: SKIPPED (informational only)")
                # Note: Coinglass validation is informational per research.md
                # Not implemented as blocking gate

            self._finalize_run(pipeline_run, started_at)

            if pipeline_config.verbose:
                print(f"\n✅ Pipeline completed in {pipeline_run.duration_seconds}s")
                print(f"   Status: {pipeline_run.status.value}")
                if pipeline_run.gate_2_decision != GateDecision.SKIP:
                    print(f"   Gate 2: {pipeline_run.gate_2_decision.value}")

            return pipeline_run

        except Exception as e:
            if pipeline_config.verbose:
                print(f"\n❌ Pipeline failed: {e}")
            return self._handle_failure(pipeline_run, started_at, e)

    def _initialize_run(
        self,
        run_id: str,
        started_at: datetime,
        config: PipelineConfig,
    ) -> ValidationPipelineRun:
        """Build the initial pipeline run state."""
        return ValidationPipelineRun(
            run_id=run_id,
            started_at=started_at,
            trigger_type=config.trigger_type,
            triggered_by=config.triggered_by,
            symbol=config.symbol,
            status=PipelineStatus.RUNNING,
            validation_types=config.validation_types,
            config={
                "tolerance_pct": config.tolerance_pct,
                "prediction_horizon_minutes": config.prediction_horizon_minutes,
                "start_date": config.start_date.isoformat() if config.start_date else None,
                "end_date": config.end_date.isoformat() if config.end_date else None,
            },
        )

    def _should_run(self, v_type: ValidationType, requested: list[ValidationType]) -> bool:
        """Return whether a given validation type should run."""
        return v_type in requested or ValidationType.FULL in requested

    def _execute_backtest_step(
        self,
        pipeline_run: ValidationPipelineRun,
        config: PipelineConfig,
    ) -> None:
        """Execute the backtest stage and apply the resulting metrics."""
        backtest_result = self._run_backtest(
            symbol=config.symbol,
            start_date=config.start_date,
            end_date=config.end_date,
            tolerance_pct=config.tolerance_pct,
            prediction_horizon_minutes=config.prediction_horizon_minutes,
            verbose=config.verbose,
        )

        if backtest_result.error:
            pipeline_run.status = PipelineStatus.FAILED
            pipeline_run.error_message = backtest_result.error
            return

        pipeline_run.backtest_result_id = f"backtest_{pipeline_run.run_id}"
        self._apply_metrics(pipeline_run, backtest_result.metrics.f1_score, config.verbose)

    def _apply_metrics(
        self,
        pipeline_run: ValidationPipelineRun,
        f1_score: float,
        verbose: bool = False,
    ) -> None:
        """Apply gate and score decisions from a backtest result."""
        decision, reason = evaluate_gate_2(f1_score)
        pipeline_run.gate_2_decision = decision
        pipeline_run.gate_2_reason = reason
        pipeline_run.overall_grade = compute_overall_grade(f1_score)
        pipeline_run.overall_score = compute_overall_score(f1_score)

        if verbose:
            gate_emoji = (
                "✅" if decision == GateDecision.PASS else ("⚠️" if decision == GateDecision.ACCEPTABLE else "❌")
            )
            print(f"\n{gate_emoji} Gate 2: {reason}")
            print(f"   Grade: {pipeline_run.overall_grade}")

    def _finalize_run(self, pipeline_run: ValidationPipelineRun, started_at: datetime) -> None:
        """Finalize a pipeline run after successful orchestration."""
        if pipeline_run.status == PipelineStatus.RUNNING:
            pipeline_run.status = PipelineStatus.COMPLETED
        pipeline_run.completed_at = datetime.now()
        pipeline_run.duration_seconds = int((pipeline_run.completed_at - started_at).total_seconds())

    def _handle_failure(
        self,
        pipeline_run: ValidationPipelineRun,
        started_at: datetime,
        exc: Exception,
    ) -> ValidationPipelineRun:
        """Finalize a failed pipeline run."""
        pipeline_run.status = PipelineStatus.FAILED
        pipeline_run.error_message = str(exc)
        pipeline_run.completed_at = datetime.now()
        pipeline_run.duration_seconds = int((pipeline_run.completed_at - started_at).total_seconds())
        return pipeline_run

    def _run_backtest(
        self,
        symbol: str,
        start_date: datetime | None,
        end_date: datetime | None,
        tolerance_pct: float,
        prediction_horizon_minutes: int,
        verbose: bool,
    ) -> BacktestResult:
        """Run backtest validation.

        Args:
            symbol: Trading pair
            start_date: Start of backtest period
            end_date: End of backtest period
            tolerance_pct: Price tolerance
            prediction_horizon_minutes: Prediction window
            verbose: Print progress

        Returns:
            BacktestResult from backtest module
        """
        # Default dates: last 30 days
        if end_date is None:
            end_date = datetime.now() - timedelta(days=1)
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        if verbose:
            print("\n📊 Running backtest...")
            print(f"   Period: {start_date.date()} to {end_date.date()}")
            print(f"   Tolerance: {tolerance_pct}%")

        config = BacktestConfig(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            tolerance_pct=tolerance_pct,
            prediction_horizon_minutes=prediction_horizon_minutes,
            db_path=self.db_path,
        )

        result = self.backtest_runner(config, verbose=verbose)

        if verbose and not result.error:
            print(f"   F1: {result.metrics.f1_score:.2%}")
            print(f"   Precision: {result.metrics.precision:.2%}")
            print(f"   Recall: {result.metrics.recall:.2%}")
            print(f"   Snapshots: {result.snapshots_analyzed}")

        return result

    def extract_backtest_summary(
        self, result: BacktestResult, result_id: str
    ) -> BacktestResultSummary:
        """Extract summary from full backtest result.

        Args:
            result: Full BacktestResult
            result_id: Unique identifier for this result

        Returns:
            BacktestResultSummary for storage/display
        """
        return BacktestResultSummary(
            result_id=result_id,
            symbol=result.config.symbol,
            start_date=result.config.start_date,
            end_date=result.config.end_date,
            f1_score=result.metrics.f1_score,
            precision=result.metrics.precision,
            recall=result.metrics.recall,
            true_positives=result.true_positives,
            false_positives=result.false_positives,
            false_negatives=result.false_negatives,
            snapshots_analyzed=result.snapshots_analyzed,
            processing_time_ms=result.processing_time_ms,
            gate_passed=result.passed_gate(0.6),
            tolerance_pct=result.config.tolerance_pct,
            error_message=result.error if result.error else None,
        )


def run_pipeline(
    symbol: str = "BTCUSDT",
    validation_types: list[str] | None = None,
    trigger_type: str = "manual",
    triggered_by: str = "system",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    tolerance_pct: float = 2.0,
    db_path: str = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb",
    verbose: bool = False,
) -> ValidationPipelineRun:
    """Convenience function to run validation pipeline.

    Args:
        symbol: Trading pair
        validation_types: List of validation type strings
        trigger_type: Trigger type string
        triggered_by: User/system identifier
        start_date: Backtest start
        end_date: Backtest end
        tolerance_pct: Price tolerance
        db_path: Database path
        verbose: Print progress

    Returns:
        ValidationPipelineRun with results
    """
    # Convert string types to enums
    vt_list: list[ValidationType] | None = None
    if validation_types:
        vt_list = [ValidationType(vt) for vt in validation_types]

    orchestrator = PipelineOrchestrator(db_path=db_path)

    return orchestrator.run_pipeline(
        symbol=symbol,
        validation_types=vt_list,
        trigger_type=TriggerType(trigger_type),
        triggered_by=triggered_by,
        start_date=start_date,
        end_date=end_date,
        tolerance_pct=tolerance_pct,
        verbose=verbose,
    )
