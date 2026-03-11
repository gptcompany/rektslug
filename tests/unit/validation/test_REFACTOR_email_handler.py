"""Unit tests for REFACTORED email handler."""

import pytest
from unittest.mock import MagicMock, patch
from src.validation.alerts.email_handler import EmailHandler

class TestREFACTOREmailHandler:
    def test_build_subject(self):
        """Should build correct subject line with emoji."""
        ctx = {"grade": "F", "model_name": "BTC", "score": 35.5}
        subject = EmailHandler().build_subject(ctx)
        assert "🚨" in subject
        assert "Grade F" in subject
        assert "35.5" in subject

    def test_build_body(self):
        """Should build HTML body with test details."""
        ctx = {
            "grade": "C", 
            "model_name": "ETH", 
            "score": 55.0,
            "run_id": "123",
            "failed_tests": 1,
            "total_tests": 2,
            "test_details": [
                {"name": "Test1", "passed": True, "score": 90},
                {"name": "Test2", "passed": False, "score": 20},
            ]
        }
        body = EmailHandler().build_body(ctx)
        assert "Grade C" in body
        assert "ETH" in body
        assert "Test1" in body
        assert "Test2" in body
        assert "PASS" in body
        assert "FAIL" in body

    def test_send_alert_no_recipients(self):
        """Should return False if no recipients configured."""
        handler = EmailHandler(to_emails=[])
        assert handler.send_alert({}) is False

    def test_send_raw_email_success(self):
        """Should successfully use the mock SMTP factory."""
        mock_server = MagicMock()
        mock_factory = MagicMock(return_value=mock_server)
        mock_server.__enter__.return_value = mock_server
        
        handler = EmailHandler(
            to_emails=["test@test.com"],
            smtp_user="user",
            smtp_password="pwd",
            smtp_factory=mock_factory
        )
        
        result = handler._send_raw_email("Sub", "Body")
        
        assert result is True
        assert mock_server.starttls.called
        assert mock_server.login.called
        assert mock_server.send_message.called

    def test_send_raw_email_failure(self):
        """Should handle SMTP connection errors."""
        mock_factory = MagicMock(side_effect=Exception("Connection refused"))
        
        handler = EmailHandler(
            to_emails=["test@test.com"],
            smtp_factory=mock_factory
        )
        
        result = handler._send_raw_email("Sub", "Body")
        assert result is False
