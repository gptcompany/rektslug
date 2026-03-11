"""Unit tests for orchestrator refactor-compatible seams."""

from unittest.mock import MagicMock
from datetime import datetime
from src.validation.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig
from src.validation.pipeline.models import (
    ValidationType,
    PipelineStatus,
    GateDecision,
)
from src.liquidationheatmap.validation.backtest import BacktestResult

class TestREFACTOROrchestrator:
    def test_run_pipeline_success(self):
        """Should complete pipeline successfully with mock runner."""
        # Setup mock result
        mock_result = MagicMock(spec=BacktestResult)
        mock_result.error = None
        mock_result.metrics = MagicMock()
        mock_result.metrics.f1_score = 0.85
        
        # Setup mock runner (Dependency Injection)
        mock_runner = MagicMock(return_value=mock_result)
        
        orchestrator = PipelineOrchestrator(
            db_path=":memory:",
            reports_dir="/tmp/reports",
            backtest_runner=mock_runner
        )
        
        config = PipelineConfig(
            symbol="BTCUSDT",
            validation_types=[ValidationType.BACKTEST],
            verbose=False
        )
        
        run = orchestrator.run_pipeline(config)
        
        assert run.status == PipelineStatus.COMPLETED
        assert run.gate_2_decision == GateDecision.PASS
        assert run.overall_grade == "A"
        assert mock_runner.called

    def test_run_pipeline_backtest_failure(self):
        """Should mark pipeline as failed if backtest fails."""
        mock_result = MagicMock(spec=BacktestResult)
        mock_result.error = "Database error"
        
        mock_runner = MagicMock(return_value=mock_result)
        
        orchestrator = PipelineOrchestrator(backtest_runner=mock_runner)
        config = PipelineConfig(validation_types=[ValidationType.BACKTEST])
        
        run = orchestrator.run_pipeline(config)
        
        assert run.status == PipelineStatus.FAILED
        assert run.error_message == "Database error"

    def test_run_pipeline_unhandled_exception(self):
        """Should handle unhandled exceptions in pipeline steps."""
        mock_runner = MagicMock(side_effect=RuntimeError("Unexpected crash"))
        
        orchestrator = PipelineOrchestrator(backtest_runner=mock_runner)
        config = PipelineConfig(validation_types=[ValidationType.BACKTEST])
        
        run = orchestrator.run_pipeline(config)
        
        assert run.status == PipelineStatus.FAILED
        assert "Unexpected crash" in run.error_message

    def test_should_run_logic(self):
        """Should correctly identify which steps to run."""
        orchestrator = PipelineOrchestrator()
        
        # Full validation should trigger backtest
        assert orchestrator._should_run(ValidationType.BACKTEST, [ValidationType.FULL]) is True
        # Coinglass only should NOT trigger backtest
        assert orchestrator._should_run(ValidationType.BACKTEST, [ValidationType.COINGLASS]) is False
        # Specific backtest should trigger it
        assert orchestrator._should_run(ValidationType.BACKTEST, [ValidationType.BACKTEST]) is True

    def test_initialize_run_config_persistence(self):
        """Should persist configuration in the run object."""
        orchestrator = PipelineOrchestrator()
        start = datetime(2024, 1, 1)
        config = PipelineConfig(symbol="ETHUSDT", start_date=start, tolerance_pct=1.5)
        
        run = orchestrator._initialize_run("id1", datetime.now(), config)
        
        assert run.symbol == "ETHUSDT"
        assert run.config["tolerance_pct"] == 1.5
        assert run.config["start_date"] == start.isoformat()
