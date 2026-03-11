"""REFACTORED Email notification handler for validation alerts.

Implements structural refactoring for 100% testability:
1. De-coupled SMTP protocol (Dependency Injection)
2. Pure logic extraction for HTML template building
3. Exception handling without side-effects in logic
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Protocol, Any

from src.validation.logger import logger

class SMTPSession(Protocol):
    """Protocol for SMTP session to allow easy mocking."""
    def starttls(self) -> Any: ...
    def login(self, user: str, password: str) -> Any: ...
    def send_message(self, msg: Any) -> Any: ...
    def quit(self) -> Any: ...
    def __enter__(self) -> 'SMTPSession': ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

class EmailHandler:
    """Handles email notifications with testable logic."""

    def __init__(
        self,
        smtp_host: str = "localhost",
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_email: str = "validation@liquidationheatmap.local",
        to_emails: Optional[List[str]] = None,
        use_tls: bool = True,
        smtp_factory: Optional[Any] = None, # For DI
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.to_emails = to_emails or []
        self.use_tls = use_tls
        self.smtp_factory = smtp_factory or smtplib.SMTP

    def send_alert(self, alert_context: dict) -> bool:
        """Send email alert with validation failure details."""
        if not self.to_emails:
            logger.warning("No recipient emails configured - skipping email alert")
            return False

        try:
            subject = self.build_subject(alert_context)
            body = self.build_body(alert_context)
            return self._send_raw_email(subject, body)
        except Exception as e:
            logger.error(f"Failed to send alert email: {e}", exc_info=True)
            return False

    @staticmethod
    def build_subject(alert_context: dict) -> str:
        """PURE LOGIC: Build email subject line."""
        grade = alert_context.get("grade", "N/A")
        model_name = alert_context.get("model_name", "Unknown")
        score = alert_context.get("score", 0)
        emoji = "🚨" if grade == "F" else "⚠️"
        return f"{emoji} Validation Alert: {model_name} - Grade {grade} (Score: {score:.1f})"

    @staticmethod
    def build_body(alert_context: dict) -> str:
        """PURE LOGIC: Build email body with alert details."""
        grade = alert_context.get("grade", "N/A")
        model_name = alert_context.get("model_name", "Unknown")
        run_id = alert_context.get("run_id", "N/A")
        score = alert_context.get("score", 0)
        failed_tests = alert_context.get("failed_tests", 0)
        total_tests = alert_context.get("total_tests", 0)
        test_details = alert_context.get("test_details", [])

        grade_color = "#dc3545" if grade == "F" else "#ffc107"
        grade_emoji = "🚨" if grade == "F" else "⚠️"

        html = f"<html><body><div style='color:{grade_color}'><h1>{grade_emoji} Grade {grade}</h1></div>"
        html += f"<p>Model: {model_name}</p><p>Score: {score:.2f}/100</p><p>Run ID: {run_id}</p>"
        html += f"<p>Failed: {failed_tests}/{total_tests}</p><ul>"
        
        for test in test_details:
            status = "✅" if test.get("passed") else "❌"
            html += f"<li>{status} {test.get('name')}: {test.get('score'):.1f}/100</li>"
            
        html += "</ul></body></html>"
        return html

    def _send_raw_email(self, subject: str, body: str) -> bool:
        """IO: Send email via SMTP factory."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.to_emails)
        msg.attach(MIMEText(body, "html"))

        try:
            with self.smtp_factory(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            return False
