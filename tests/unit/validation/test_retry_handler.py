"""Unit tests for retry handler."""

from unittest.mock import MagicMock, patch
import pytest
from src.validation.retry_handler import retry_with_backoff, RetryHandler, ValidationTimeoutError

class TestRetryHandler:
    @patch("src.validation.retry_handler.time.sleep")
    def test_retry_decorator_success(self, mock_sleep):
        """Should succeed on first attempt."""
        mock_func = MagicMock(return_value="success")
        mock_func.__name__ = "mock_func"
        decorated = retry_with_backoff(max_attempts=3)(mock_func)
        
        result = decorated("arg")
        assert result == "success"
        assert mock_func.call_count == 1
        assert mock_sleep.call_count == 0

    @patch("src.validation.retry_handler.time.sleep")
    def test_retry_decorator_fail_then_succeed(self, mock_sleep):
        """Should succeed on second attempt."""
        mock_func = MagicMock(side_effect=[ValueError("fail"), "success"])
        mock_func.__name__ = "mock_func"
        decorated = retry_with_backoff(max_attempts=3, backoff_base=0.1)(mock_func)
        
        result = decorated()
        assert result == "success"
        assert mock_func.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("src.validation.retry_handler.time.sleep")
    def test_retry_decorator_all_fail(self, mock_sleep):
        """Should raise exception after all attempts fail."""
        mock_func = MagicMock(side_effect=ValueError("fail"))
        mock_func.__name__ = "mock_func"
        decorated = retry_with_backoff(max_attempts=3, backoff_base=0.1)(mock_func)
        
        with pytest.raises(ValueError, match="fail"):
            decorated()
        assert mock_func.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("src.validation.retry_handler.time.sleep")
    def test_retry_handler_execute_success(self, mock_sleep):
        """Should succeed on first attempt via execute_with_retry."""
        handler = RetryHandler(max_attempts=3)
        mock_func = MagicMock(return_value="success")
        mock_func.__name__ = "mock_func"
        
        result = handler.execute_with_retry(mock_func, "arg", k="v")
        assert result == "success"
        mock_func.assert_called_once_with("arg", k="v")

    @patch("src.validation.retry_handler.time.sleep")
    def test_retry_handler_execute_fail_then_succeed(self, mock_sleep):
        """Should succeed on second attempt via execute_with_retry."""
        handler = RetryHandler(max_attempts=3, backoff_base=0.1)
        mock_func = MagicMock(side_effect=[RuntimeError("fail"), "success"])
        mock_func.__name__ = "mock_func"
        
        result = handler.execute_with_retry(mock_func, exceptions=(RuntimeError,))
        assert result == "success"
        assert mock_func.call_count == 2
        assert mock_sleep.call_count == 1
