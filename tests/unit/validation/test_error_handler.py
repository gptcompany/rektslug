"""Unit tests for error handler middleware."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import Request, FastAPI
from src.validation.middleware.error_handler import production_error_handler, configure_error_handlers

class TestErrorHandler:
    @pytest.mark.asyncio
    async def test_production_error_handler_dev_mode(self):
        """Should show error details in dev mode."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url = "http://test.com"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        
        exc = ValueError("Secret error")
        
        with patch("src.validation.middleware.error_handler.get_security_settings") as mock_settings:
            mock_settings.return_value = MagicMock(log_error_details=True, show_error_details=True)
            response = await production_error_handler(request, exc)
            
        assert response.status_code == 500
        data = response.body.decode()
        assert "Secret error" in data
        assert "ValueError" in data

    @pytest.mark.asyncio
    async def test_production_error_handler_prod_mode(self):
        """Should hide error details in prod mode."""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url = "http://test.com"
        request.client = None
        
        exc = ValueError("Secret error")
        
        with patch("src.validation.middleware.error_handler.get_security_settings") as mock_settings:
            mock_settings.return_value = MagicMock(log_error_details=True, show_error_details=False)
            response = await production_error_handler(request, exc)
            
        assert response.status_code == 500
        data = response.body.decode()
        assert "Secret error" not in data
        assert "An unexpected error occurred" in data

    def test_configure_error_handlers(self):
        """Should add exception handler to FastAPI app."""
        app = MagicMock(spec=FastAPI)
        configure_error_handlers(app)
        app.add_exception_handler.assert_called_once()
