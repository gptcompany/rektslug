"""
Validation API endpoints for manual validation triggers.

Provides REST API endpoints for triggering validation runs,
checking status, and retrieving reports.
"""

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.validation_run import ValidationStatus
from src.validation.logger import logger
from src.validation.storage import ValidationStorage
from src.exchanges.binance import BinanceAdapter
from src.validation.margin_validator import MarginValidator

router = APIRouter(prefix="/api/validation", tags=["validation"])


# Request/Response Models
class ValidationTriggerRequest(BaseModel):
    """Request to trigger a validation run."""

    model_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name of model to validate",
        pattern=r"^[a-zA-Z0-9_\-\.]+$",
    )
    triggered_by: str = Field(
        default="api", min_length=1, max_length=200, description="User ID or system identifier"
    )
    data_start_date: Optional[str] = Field(
        None, description="Start date for validation data (ISO format: YYYY-MM-DD)"
    )
    data_end_date: Optional[str] = Field(
        None, description="End date for validation data (ISO format: YYYY-MM-DD)"
    )

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Validate and sanitize model name."""
        # Remove any potential injection characters
        sanitized = re.sub(r"[^\w\-\.]", "", v)
        if not sanitized:
            raise ValueError("model_name must contain at least one alphanumeric character")
        if len(sanitized) > 100:
            raise ValueError("model_name must be at most 100 characters")
        return sanitized

    @field_validator("data_start_date", "data_end_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate ISO date format."""
        if v is None:
            return None
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except ValueError:
            raise ValueError(
                f"Invalid date format: {v}. Expected ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
            )

    @model_validator(mode="after")
    def validate_date_range(self):
        """Validate that end_date is after start_date."""
        if self.data_start_date and self.data_end_date:
            start = datetime.fromisoformat(self.data_start_date.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.data_end_date.replace("Z", "+00:00"))

            if end < start:
                raise ValueError("data_end_date must be after data_start_date")

            # Validate reasonable date range (max 2 years)
            delta = end - start
            if delta.days > 730:
                raise ValueError("Date range cannot exceed 2 years (730 days)")

        return self


class ValidationTriggerResponse(BaseModel):
    """Response from validation trigger."""

    run_id: str = Field(..., description="Unique validation run ID")
    status: str = Field(..., description="Initial run status")
    message: str = Field(..., description="Status message")
    estimated_duration_seconds: int = Field(default=300, description="Estimated completion time")


class ValidationStatusResponse(BaseModel):
    """Response with validation run status."""

    run_id: str
    model_name: str
    status: str
    overall_grade: Optional[str] = None
    overall_score: Optional[float] = None
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    error_message: Optional[str] = None


class ValidationReportResponse(BaseModel):
    """Response with validation report."""

    run_id: str
    model_name: str
    format: str
    report_content: str
    summary: dict
    recommendations: list
    generated_at: str


class MarginValidationRequest(BaseModel):
    """Request to trigger margin validation."""
    triggered_by: str = Field(
        default="api", min_length=1, max_length=200, description="User ID or system identifier"
    )

class MarginValidationResponse(BaseModel):
    """Response from margin validation."""
    status: str = Field(..., description="Status of the margin validation")
    message: str = Field(..., description="Detailed message about the validation result")
    account_info: Optional[dict] = Field(None, description="Raw account information from exchange")
    crossMaintenanceMarginUsed: Optional[float] = Field(None, description="Total maintenance margin used in cross margin mode")


# API Endpoints
@router.post("/margin", response_model=MarginValidationResponse)
async def validate_margin(
    request: MarginValidationRequest,
) -> MarginValidationResponse:
    """
    Triggers a margin validation check for the configured Binance account.

    Args:
        request: Margin validation request.

    Returns:
        MarginValidationResponse with the validation status and details.
    """
    logger.info(f"Margin validation request received, triggered by: {request.triggered_by}")

    try:
        binance_adapter = BinanceAdapter()
        await binance_adapter.connect() # Ensure connection is established
        margin_validator = MarginValidator(binance_adapter)
        
        validation_result = await margin_validator.validate_account_margin()
        
        await binance_adapter.disconnect() # Disconnect after use

        return MarginValidationResponse(
            status=validation_result.get("status", "error"),
            message=validation_result.get("message", "Unknown error during validation."),
            account_info=validation_result.get("account_info"),
            crossMaintenanceMarginUsed=validation_result.get("crossMaintenanceMarginUsed"),
        )
    except Exception as e:
        logger.error(f"Failed to perform margin validation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to perform margin validation: {str(e)}")


@router.post("/run", response_model=ValidationTriggerResponse, status_code=202)
async def trigger_validation(
    request: ValidationTriggerRequest,
    background_tasks: BackgroundTasks,
) -> ValidationTriggerResponse:
    """
    Trigger a manual validation run.

    This endpoint queues a validation run to be executed in the background.
    Use the returned run_id to check status and retrieve results.

    Args:
        request: Validation trigger request
        background_tasks: FastAPI background tasks

    Returns:
        ValidationTriggerResponse with run_id and status

    Example:
        POST /api/validation/run
        {
            "model_name": "liquidation_model_v1",
            "triggered_by": "user@example.com"
        }
    """
    logger.info(
        f"Validation trigger request received: model={request.model_name}, "
        f"triggered_by={request.triggered_by}"
    )

    try:
        # Import here to avoid circular dependency
        from src.validation.test_runner import ValidationTestRunner

        # Create test runner
        runner = ValidationTestRunner(
            model_name=request.model_name,
            trigger_type="manual",
            triggered_by=request.triggered_by,
        )

        run_id = runner.run_id

        # Queue validation run in background
        # Note: In production, this would use the queue manager (T031)
        # For now, run directly in background task
        background_tasks.add_task(
            _execute_validation_background,
            runner=runner,
            run_id=run_id,
        )

        logger.info(f"Validation run queued: {run_id}")

        return ValidationTriggerResponse(
            run_id=run_id,
            status="queued",
            message=f"Validation run {run_id} queued for execution",
            estimated_duration_seconds=300,  # 5 minutes
        )

    except Exception as e:
        logger.error(f"Failed to trigger validation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to trigger validation: {str(e)}")


@router.get("/status/{run_id}", response_model=ValidationStatusResponse)
async def get_validation_status(
    run_id: str = Path(
        ...,
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="UUID of the validation run",
    ),
) -> ValidationStatusResponse:
    """
    Get status of a validation run.

    Args:
        run_id: Validation run ID

    Returns:
        ValidationStatusResponse with current status

    Example:
        GET /api/validation/status/550e8400-e29b-41d4-a716-446655440000
    """
    logger.debug(f"Status request for run: {run_id}")

    try:
        # Retrieve run from storage
        with ValidationStorage() as storage:
            run = storage.get_run(run_id)

        if not run:
            raise HTTPException(status_code=404, detail=f"Validation run {run_id} not found")

        return ValidationStatusResponse(
            run_id=run.run_id,
            model_name=run.model_name,
            status=run.status.value if run.status else "unknown",
            overall_grade=run.overall_grade.value if run.overall_grade else None,
            overall_score=float(run.overall_score) if run.overall_score else None,
            started_at=run.started_at.isoformat(),
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            duration_seconds=run.duration_seconds,
            error_message=run.error_message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get validation status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve validation status: {str(e)}"
        )


@router.get("/report/{run_id}", response_model=ValidationReportResponse)
async def get_validation_report(
    run_id: str = Path(
        ...,
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="UUID of the validation run",
    ),
    format: str = Query(
        default="json",
        pattern=r"^(json|text|html)$",
        description="Report format: json, text, or html",
    ),
) -> ValidationReportResponse:
    """
    Get validation report for a completed run.

    Args:
        run_id: Validation run ID
        format: Report format (json, text, html)

    Returns:
        ValidationReportResponse with report content

    Example:
        GET /api/validation/report/550e8400-e29b-41d4-a716-446655440000?format=json
    """
    logger.debug(f"Report request for run: {run_id}, format: {format}")

    try:
        # Retrieve run and report from storage
        with ValidationStorage() as storage:
            run = storage.get_run(run_id)
            if not run:
                raise HTTPException(status_code=404, detail=f"Validation run {run_id} not found")

            # Check if run is completed
            if run.status != ValidationStatus.COMPLETED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Validation run {run_id} is not completed (status: {run.status.value})",
                )

            # Get report with requested format
            reports = storage.get_reports_for_run(run_id)

            # Find report with requested format
            report = None
            for r in reports:
                if r.format.value == format:
                    report = r
                    break

            if not report:
                raise HTTPException(
                    status_code=404,
                    detail=f"Report with format '{format}' not found for run {run_id}",
                )

        return ValidationReportResponse(
            run_id=report.run_id,
            model_name=run.model_name,
            format=report.format.value,
            report_content=report.report_content,
            summary=report.summary,
            recommendations=report.recommendations,
            generated_at=report.created_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get validation report: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve validation report: {str(e)}"
        )


# Background task functions
async def _execute_validation_background(runner, run_id: str):
    """
    Execute validation run in background.

    Args:
        runner: ValidationTestRunner instance
        run_id: Validation run ID
    """
    logger.info(f"Starting background validation execution: {run_id}")

    try:
        # Execute validation tests
        # Note: In production, would fetch real data here
        run, tests = runner.run_all_tests(
            funding_data=None,  # Would fetch from data_fetcher
            oi_data=None,  # Would fetch from data_fetcher
            directional_data=None,  # Would fetch from data_fetcher
        )

        # Generate reports
        from src.validation.reports.json_reporter import JSONReporter
        from src.validation.reports.text_reporter import TextReporter

        json_reporter = JSONReporter()
        text_reporter = TextReporter()

        json_report = json_reporter.generate_report(run, tests)
        text_report = text_reporter.generate_report(run, tests)

        # Persist results
        with ValidationStorage() as storage:
            storage.save_run(run)
            for test in tests:
                storage.save_test(test)
            storage.save_report(json_report)
            storage.save_report(text_report)

        # Trigger alerts if needed
        from src.validation.alerts.alert_manager import AlertManager

        alert_manager = AlertManager()
        if alert_manager.should_trigger_alert(run):
            alert_manager.process_run(run, tests)

        logger.info(
            f"Background validation completed: {run_id}, "
            f"grade={run.overall_grade.value if run.overall_grade else 'N/A'}"
        )

    except Exception as e:
        logger.error(f"Background validation failed: {run_id}, error: {e}", exc_info=True)

        # Update run status to failed
        try:
            with ValidationStorage() as storage:
                run = storage.get_run(run_id)
                if run:
                    run.status = ValidationStatus.FAILED
                    run.error_message = str(e)
                    run.completed_at = datetime.utcnow()
                    storage.save_run(run)
        except Exception as update_error:
            logger.error(f"Failed to update run status: {update_error}")
