"""Pipeline orchestrator for coordinating validation runs.

Orchestrates backtest validation and optional Coinglass comparison,
implementing Gate 2 decision logic per specs/014-validation-pipeline/plan.md.
"""

import uuid
from datetime import datetime, timedelta
from pathlib import Path

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
    ):
        """Initialize orchestrator.

        Args:
            db_path: Path to DuckDB database
            reports_dir: Directory for output reports
        """
        self.db_path = db_path
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def run_pipeline(
        self,
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
        if validation_types is None:
            validation_types = [ValidationType.BACKTEST]

        # Generate run ID
        run_id = str(uuid.uuid4())
        started_at = datetime.now()

        # Initialize pipeline run
        pipeline_run = ValidationPipelineRun(
            run_id=run_id,
            started_at=started_at,
            trigger_type=trigger_type,
            triggered_by=triggered_by,
            symbol=symbol,
            status=PipelineStatus.RUNNING,
            validation_types=validation_types,
            config={
                "tolerance_pct": tolerance_pct,
                "prediction_horizon_minutes": prediction_horizon_minutes,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
            },
        )

        if verbose:
            print(f"🚀 Starting validation pipeline: {run_id}")
            print(f"   Symbol: {symbol}")
            print(f"   Validation types: {[vt.value for vt in validation_types]}")

        try:
            # Run backtest if requested
            backtest_result: BacktestResult | None = None
            if (
                ValidationType.BACKTEST in validation_types
                or ValidationType.FULL in validation_types
            ):
                backtest_result = self._run_backtest(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    tolerance_pct=tolerance_pct,
                    prediction_horizon_minutes=prediction_horizon_minutes,
                    verbose=verbose,
                )

                if backtest_result.error:
                    pipeline_run.status = PipelineStatus.FAILED
                    pipeline_run.error_message = backtest_result.error
                else:
                    # Store backtest result reference
                    pipeline_run.backtest_result_id = f"backtest_{run_id}"

                    # Evaluate Gate 2
                    decision, reason = evaluate_gate_2(backtest_result.metrics.f1_score)
                    pipeline_run.gate_2_decision = decision
                    pipeline_run.gate_2_reason = reason

                    # Compute overall grade and score
                    pipeline_run.overall_grade = compute_overall_grade(
                        backtest_result.metrics.f1_score
                    )
                    pipeline_run.overall_score = compute_overall_score(
                        backtest_result.metrics.f1_score
                    )

                    if verbose:
                        gate_emoji = (
                            "✅"
                            if decision == GateDecision.PASS
                            else ("⚠️" if decision == GateDecision.ACCEPTABLE else "❌")
                        )
                        print(f"\n{gate_emoji} Gate 2: {reason}")
                        print(f"   Grade: {pipeline_run.overall_grade}")

            # Run Coinglass comparison if requested (informational only)
            if (
                ValidationType.COINGLASS in validation_types
                or ValidationType.FULL in validation_types
            ):
                if verbose:
                    print("\n📊 Coinglass comparison: SKIPPED (informational only)")
                # Note: Coinglass validation is informational per research.md
                # Not implemented as blocking gate

            # Mark completed
            if pipeline_run.status == PipelineStatus.RUNNING:
                pipeline_run.status = PipelineStatus.COMPLETED

            pipeline_run.completed_at = datetime.now()
            pipeline_run.duration_seconds = int(
                (pipeline_run.completed_at - started_at).total_seconds()
            )

            if verbose:
                print(f"\n✅ Pipeline completed in {pipeline_run.duration_seconds}s")
                print(f"   Status: {pipeline_run.status.value}")
                if pipeline_run.gate_2_decision != GateDecision.SKIP:
                    print(f"   Gate 2: {pipeline_run.gate_2_decision.value}")

            return pipeline_run

        except Exception as e:
            pipeline_run.status = PipelineStatus.FAILED
            pipeline_run.error_message = str(e)
            pipeline_run.completed_at = datetime.now()
            pipeline_run.duration_seconds = int(
                (pipeline_run.completed_at - started_at).total_seconds()
            )

            if verbose:
                print(f"\n❌ Pipeline failed: {e}")

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

        result = run_backtest(config, verbose=verbose)

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
