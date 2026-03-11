"""Unit tests for validation scheduler."""

from unittest.mock import MagicMock, patch
import pytest
from src.validation.scheduler import ValidationScheduler

class TestValidationScheduler:
    @patch("src.validation.scheduler.BackgroundScheduler")
    def test_init(self, mock_scheduler_cls):
        """Should start scheduler on init."""
        mock_scheduler = mock_scheduler_cls.return_value
        scheduler = ValidationScheduler()
        assert mock_scheduler.start.called

    @patch("src.validation.scheduler.BackgroundScheduler")
    @patch("src.validation.scheduler.CronTrigger")
    def test_schedule_weekly_validation(self, mock_trigger_cls, mock_scheduler_cls):
        """Should add weekly job to scheduler."""
        mock_scheduler = mock_scheduler_cls.return_value
        scheduler = ValidationScheduler()
        
        callback = MagicMock()
        scheduler.schedule_weekly_validation(callback, "test_model")
        
        assert mock_scheduler.add_job.called
        args, kwargs = mock_scheduler.add_job.call_args
        assert args[0] == callback
        assert kwargs["id"] == "weekly_validation_test_model"

    @patch("src.validation.scheduler.BackgroundScheduler")
    def test_trigger_manual_validation(self, mock_scheduler_cls):
        """Should add immediate job to scheduler."""
        mock_scheduler = mock_scheduler_cls.return_value
        scheduler = ValidationScheduler()
        
        callback = MagicMock()
        scheduler.trigger_manual_validation(callback, "test_model", "user1")
        
        assert mock_scheduler.add_job.called
        args, kwargs = mock_scheduler.add_job.call_args
        assert args[0] == callback
        assert kwargs["id"] == "manual_validation_test_model_user1"

    @patch("src.validation.scheduler.BackgroundScheduler")
    def test_get_scheduled_jobs(self, mock_scheduler_cls):
        """Should return jobs from scheduler."""
        mock_scheduler = mock_scheduler_cls.return_value
        mock_scheduler.get_jobs.return_value = ["job1"]
        scheduler = ValidationScheduler()
        
        assert scheduler.get_scheduled_jobs() == ["job1"]

    @patch("src.validation.scheduler.BackgroundScheduler")
    def test_remove_job(self, mock_scheduler_cls):
        """Should remove job from scheduler."""
        mock_scheduler = mock_scheduler_cls.return_value
        scheduler = ValidationScheduler()
        
        scheduler.remove_job("job1")
        mock_scheduler.remove_job.assert_called_once_with("job1")

    @patch("src.validation.scheduler.BackgroundScheduler")
    def test_shutdown(self, mock_scheduler_cls):
        """Should shutdown scheduler."""
        mock_scheduler = mock_scheduler_cls.return_value
        scheduler = ValidationScheduler()
        
        scheduler.shutdown(wait=False)
        mock_scheduler.shutdown.assert_called_once_with(wait=False)
