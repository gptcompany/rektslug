"""Unit tests for validation cron jobs."""

from unittest.mock import MagicMock, patch
import pytest
from src.validation.cron_jobs import run_scheduled_validation, setup_weekly_validation

class TestCronJobs:
    @patch("src.validation.cron_jobs.ValidationTestRunner")
    @patch("src.validation.cron_jobs.ValidationStorage")
    def test_run_scheduled_validation_success(self, mock_storage_cls, mock_runner_cls):
        """Should run all tests and save results."""
        mock_runner = mock_runner_cls.return_value
        mock_run = MagicMock()
        mock_run.run_id = "run123"
        mock_run.overall_grade = "A"
        mock_run.overall_score = 95.0
        mock_tests = [MagicMock(), MagicMock()]
        mock_runner.run_all_tests.return_value = (mock_run, mock_tests)
        
        mock_storage = mock_storage_cls.return_value.__enter__.return_value
        
        result = run_scheduled_validation("test_model", "scheduled", "system")
        
        assert result == mock_run
        assert mock_runner.run_all_tests.called
        assert mock_storage.save_run.called
        assert mock_storage.save_test.call_count == 2

    @patch("src.validation.cron_jobs.ValidationTestRunner")
    def test_run_scheduled_validation_failure(self, mock_runner_cls):
        """Should raise exception if validation fails."""
        mock_runner = mock_runner_cls.return_value
        mock_runner.run_all_tests.side_effect = RuntimeError("Validation failed")
        
        with pytest.raises(RuntimeError, match="Validation failed"):
            run_scheduled_validation("test_model", "scheduled", "system")

    @patch("src.validation.cron_jobs.ValidationScheduler")
    def test_setup_weekly_validation(self, mock_scheduler_cls):
        """Should initialize scheduler and schedule job."""
        mock_scheduler = mock_scheduler_cls.return_value
        mock_job = MagicMock()
        mock_job.id = "job123"
        mock_scheduler.schedule_weekly_validation.return_value = mock_job
        
        scheduler = setup_weekly_validation("test_model")
        
        assert scheduler == mock_scheduler
        assert mock_scheduler.schedule_weekly_validation.called
        args, kwargs = mock_scheduler.schedule_weekly_validation.call_args
        assert kwargs["model_name"] == "test_model"
        assert kwargs["validation_callback"] == run_scheduled_validation
