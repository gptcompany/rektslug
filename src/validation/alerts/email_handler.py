"""
Email notification handler for validation alerts.

Sends email alerts when validation runs fail with C or F grades.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, List, Optional

from src.validation.logger import logger


class EmailHandler:
    """
    Handles email notifications for validation alerts.

    Sends formatted email alerts via SMTP when validation failures occur.
    """

    def __init__(
        self,
        smtp_host: str = "localhost",
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_email: str = "validation@liquidationheatmap.local",
        to_emails: Optional[List[str]] = None,
        use_tls: bool = True,
        smtp_factory: Any = None,
    ):
        """
        Initialize email handler.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port (587 for TLS, 465 for SSL, 25 for plain)
            smtp_user: SMTP username (if authentication required)
            smtp_password: SMTP password (if authentication required)
            from_email: Sender email address
            to_emails: List of recipient email addresses
            use_tls: Whether to use TLS encryption
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.to_emails = to_emails or []
        self.use_tls = use_tls
        self.smtp_factory = smtp_factory or smtplib.SMTP

    def send_alert(self, alert_context: dict) -> bool:
        """
        Send email alert with validation failure details.

        Args:
            alert_context: Dict with alert information from AlertManager

        Returns:
            True if email sent successfully
        """
        if not self.to_emails:
            logger.warning("No recipient emails configured - skipping email alert")
            return False

        try:
            # Build email
            subject = self.build_subject(alert_context)
            body = self.build_body(alert_context)

            # Send email
            success = self._send_email(subject, body)

            if success:
                logger.info(
                    f"Alert email sent to {len(self.to_emails)} recipients "
                    f"for run {alert_context.get('run_id')}"
                )

            return success

        except Exception as e:
            logger.error(f"Failed to send alert email: {e}", exc_info=True)
            return False

    def build_subject(self, alert_context: dict) -> str:
        """Public testable wrapper for subject generation."""
        return self._build_subject(alert_context)

    def build_body(self, alert_context: dict) -> str:
        """Public testable wrapper for body generation."""
        return self._build_body(alert_context)

    def _build_subject(self, alert_context: dict) -> str:
        """
        Build email subject line.

        Args:
            alert_context: Alert context dict

        Returns:
            Email subject string
        """
        grade = alert_context.get("grade", "N/A")
        model_name = alert_context.get("model_name", "Unknown")
        score = alert_context.get("score", 0)

        emoji = "🚨" if grade == "F" else "⚠️"

        return f"{emoji} Validation Alert: {model_name} - Grade {grade} (Score: {score:.1f})"

    def _build_body(self, alert_context: dict) -> str:
        """
        Build email body with alert details.

        Args:
            alert_context: Alert context dict

        Returns:
            Formatted email body (HTML)
        """
        grade = alert_context.get("grade", "N/A")
        model_name = alert_context.get("model_name", "Unknown")
        run_id = alert_context.get("run_id", "N/A")
        score = alert_context.get("score", 0)
        failed_tests = alert_context.get("failed_tests", 0)
        total_tests = alert_context.get("total_tests", 0)
        test_details = alert_context.get("test_details", [])

        # Grade styling
        grade_color = "#dc3545" if grade == "F" else "#ffc107"  # Red for F, yellow for C
        grade_emoji = "🚨" if grade == "F" else "⚠️"

        # Build HTML email
        html = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: {grade_color};
                    color: white;
                    padding: 20px;
                    border-radius: 5px;
                    text-align: center;
                }}
                .summary {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .summary-item {{
                    margin: 10px 0;
                }}
                .summary-label {{
                    font-weight: bold;
                    color: #495057;
                }}
                .tests-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }}
                .tests-table th {{
                    background-color: #343a40;
                    color: white;
                    padding: 12px;
                    text-align: left;
                }}
                .tests-table td {{
                    padding: 10px;
                    border-bottom: 1px solid #dee2e6;
                }}
                .test-passed {{
                    color: #28a745;
                }}
                .test-failed {{
                    color: #dc3545;
                    font-weight: bold;
                }}
                .actions {{
                    background-color: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 15px;
                    margin: 20px 0;
                }}
                .actions h3 {{
                    margin-top: 0;
                    color: #856404;
                }}
                .actions ul {{
                    margin: 10px 0;
                }}
                .footer {{
                    text-align: center;
                    color: #6c757d;
                    font-size: 0.9em;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #dee2e6;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{grade_emoji} Validation Alert - Grade {grade}</h1>
                <p>Model validation has detected performance degradation</p>
            </div>

            <div class="summary">
                <h2>Summary</h2>
                <div class="summary-item">
                    <span class="summary-label">Model:</span> {model_name}
                </div>
                <div class="summary-item">
                    <span class="summary-label">Grade:</span>
                    <span style="color: {grade_color}; font-weight: bold; font-size: 1.2em;">{grade}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">Score:</span> {score:.2f}/100
                </div>
                <div class="summary-item">
                    <span class="summary-label">Run ID:</span> {run_id}
                </div>
                <div class="summary-item">
                    <span class="summary-label">Failed Tests:</span> {failed_tests}/{total_tests}
                </div>
            </div>

            <h2>Test Results</h2>
            <table class="tests-table">
                <thead>
                    <tr>
                        <th>Test Name</th>
                        <th>Status</th>
                        <th>Score</th>
                        <th>Weight</th>
                    </tr>
                </thead>
                <tbody>
        """

        # Add test rows
        for test in test_details:
            status_class = "test-passed" if test["passed"] else "test-failed"
            status_icon = "✅" if test["passed"] else "❌"
            status_text = "PASS" if test["passed"] else "FAIL"

            html += f"""
                    <tr>
                        <td>{test["name"]}</td>
                        <td class="{status_class}">{status_icon} {status_text}</td>
                        <td>{test["score"]:.1f}/100</td>
                        <td>{test.get("weight", 0) * 100:.0f}%</td>
                    </tr>
            """

            # Add error message if test failed
            if not test["passed"] and test.get("error"):
                html += f"""
                    <tr>
                        <td colspan="4" style="padding-left: 30px; color: #6c757d;">
                            <em>Error: {test["error"]}</em>
                        </td>
                    </tr>
                """

        html += """
                </tbody>
            </table>

            <div class="actions">
                <h3>Required Actions</h3>
                <ul>
                    <li>Review failed test diagnostics in validation dashboard</li>
                    <li>Investigate model performance degradation causes</li>
                    <li>Check data quality and completeness metrics</li>
                    <li>Consider model retraining or parameter adjustment</li>
                    <li>Verify market conditions haven't fundamentally changed</li>
                </ul>
            </div>

            <div class="footer">
                <p>Liquidation Model Validation Suite</p>
                <p>This is an automated alert. Do not reply to this email.</p>
            </div>
        </body>
        </html>
        """

        return html

    def _send_email(self, subject: str, body: str) -> bool:
        """
        Send email via SMTP.

        Args:
            subject: Email subject
            body: Email body (HTML)

        Returns:
            True if email sent successfully, False otherwise
        """
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.to_emails)

        # Attach HTML body
        html_part = MIMEText(body, "html")
        msg.attach(html_part)

        # Connect and send
        try:
            with self.smtp_factory(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()

                # Authenticate if credentials provided
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)

                # Send email
                server.send_message(msg)

            logger.debug(f"Email sent successfully to {self.to_emails}")
            return True

        except Exception as e:
            logger.error(f"SMTP error: {e}", exc_info=True)
            return False

    def _send_raw_email(self, subject: str, body: str) -> bool:
        """Compatibility alias for dependency-injected SMTP tests."""
        return self._send_email(subject, body)

    def test_connection(self) -> bool:
        """
        Test SMTP connection.

        Returns:
            True if connection successful
        """
        try:
            if self.use_tls:
                server = self.smtp_factory(self.smtp_host, self.smtp_port)
                server.starttls()
            else:
                server = self.smtp_factory(self.smtp_host, self.smtp_port)

            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)

            server.quit()

            logger.info(f"SMTP connection test successful: {self.smtp_host}:{self.smtp_port}")
            return True

        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False
