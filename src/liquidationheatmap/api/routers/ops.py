import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.liquidationheatmap.api.routers.signals import get_continuous_report, get_signal_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["ops", "cockpit"])

SHADOW_MANIFEST_ROOT = Path("data/validation/expert_snapshots/hyperliquid/manifests")
SHADOW_PRODUCER_SYMBOLS = ("BTCUSDT", "ETHUSDT")
SHADOW_PRODUCER_FRESHNESS_SECS = 600


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _map_continuous_report_status(
    report_status: str,
) -> Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]:
    normalized = report_status.lower()
    if normalized == "ok":
        return "HEALTHY"
    if normalized == "blocked":
        return "BLOCKED"
    if normalized == "degraded":
        return "DEGRADED"
    return "UNAVAILABLE"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _shadow_producer_status(
    *,
    repo_root: Path | None = None,
    max_age_secs: int = SHADOW_PRODUCER_FRESHNESS_SECS,
) -> Literal["HEALTHY", "UNAVAILABLE"]:
    root = repo_root or _repo_root()
    manifest_root = root / SHADOW_MANIFEST_ROOT
    now_ts = datetime.now(timezone.utc).timestamp()

    for symbol in SHADOW_PRODUCER_SYMBOLS:
        symbol_dir = manifest_root / symbol
        try:
            latest_mtime = max(
                path.stat().st_mtime for path in symbol_dir.glob("*.json") if path.is_file()
            )
        except (OSError, ValueError):
            return "UNAVAILABLE"

        if now_ts - latest_mtime > max_age_secs:
            return "UNAVAILABLE"

    return "HEALTHY"


class OpsEnvelope(BaseModel):
    provider_id: str = "rektslug"
    schema_version: str = "1.0.0"
    generated_at: str = Field(default_factory=_utc_now)
    status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]
    freshness_sla_secs: int = 60
    last_error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def _find_latest_spec040_evidence() -> dict[str, Any]:
    # Look for the spec-040 evidence
    repo_root = _repo_root()
    evidence_base = repo_root / "specs" / "040-nautilus-continuous-paper-testnet"
    if not evidence_base.exists():
        return {}

    g3_sessions = list(evidence_base.glob("g3_session/*/evidence/summary.json"))
    if not g3_sessions:
        return {}

    # Sort by the timestamp in the directory name
    g3_sessions.sort(key=lambda p: p.parent.parent.name, reverse=True)
    latest = g3_sessions[0]

    try:
        with open(latest, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read latest evidence from {latest}: {e}")
        return {}


def _format_evidence_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    report = evidence.get("continuous_report", {})

    # Try to extract a stable session identifier
    session_identifier = "unknown"
    snapshot_path = evidence.get("runtime_snapshot_path", "")
    if snapshot_path:
        session_identifier = Path(snapshot_path).parent.name

    return {
        "session_id": session_identifier,
        "retained_session_id": session_identifier,
        "verdict": evidence.get("gate_status", "UNKNOWN"),
        "status": evidence.get("gate_status", "UNKNOWN"),
        "session_timing": {
            "session_started_at": report.get("session_started_at"),
            "timestamp": report.get("timestamp"),
            "runtime_seconds": report.get("runtime_seconds"),
        },
        "feedback_published": report.get("feedback_published"),
        "feedback_persisted": report.get("feedback_persisted"),
        "positions_opened": report.get("positions_opened"),
        "positions_closed": report.get("positions_closed"),
        "residual_exposure_summary": {
            "residual_open_positions": report.get("residual_open_positions"),
            "residual_open_orders": report.get("residual_open_orders"),
        },
        "artifact_links": {
            "runtime_snapshot_path": evidence.get("runtime_snapshot_path"),
            "feedback_db_path": evidence.get("feedback_db_path"),
        },
    }


def _map_gate_status_to_envelope_status(
    gate_status: str,
) -> Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"]:
    gate_status_upper = gate_status.upper()
    if gate_status_upper in ("READY_FOR_REVIEW", "PASSED", "HEALTHY", "OK"):
        return "HEALTHY"
    elif gate_status_upper in ("BLOCKED", "FAILED", "ERROR"):
        return "BLOCKED"
    else:
        return "DEGRADED"


@router.get("/summary", response_model=OpsEnvelope)
async def ops_summary() -> OpsEnvelope:
    details = {
        "redis": "UNAVAILABLE",
        "signals_status_level": "UNAVAILABLE",
        "signals_status": None,
        "shadow_producer": "UNAVAILABLE",
        "shadow_consumer": "UNAVAILABLE",
        "feedback_consumer": "UNAVAILABLE",
        "continuous_report_status": "UNAVAILABLE",
        "evidence_spec_040_latest_status": "UNAVAILABLE",
        "shadow_report_status": "UNAVAILABLE",
        "ownership_note": "rektslug does not own execution controls or final readiness.",
        "latest_evidence_spec040": None,
    }

    status: Literal["HEALTHY", "DEGRADED", "BLOCKED", "UNAVAILABLE"] = "HEALTHY"

    try:
        sig_status = await get_signal_status()
        details["signals_status_level"] = "HEALTHY" if sig_status.connected else "DEGRADED"
        details["signals_status"] = sig_status.model_dump(mode="json")
        details["redis"] = "HEALTHY" if sig_status.connected else "UNAVAILABLE"
        if not sig_status.connected:
            status = "DEGRADED"
    except Exception:
        details["signals_status_level"] = "UNAVAILABLE"
        status = "DEGRADED"

    try:
        details["shadow_producer"] = _shadow_producer_status()
    except Exception as exc:
        logger.warning(f"Failed to inspect shadow producer freshness: {exc}")
        details["shadow_producer"] = "UNAVAILABLE"

    try:
        cont_report = await get_continuous_report()
        details["continuous_report_status"] = _map_continuous_report_status(
            cont_report.report_status
        )
        if details["continuous_report_status"] == "BLOCKED":
            status = "BLOCKED"
        elif details["continuous_report_status"] in ("DEGRADED", "UNAVAILABLE"):
            if status != "BLOCKED":
                status = "DEGRADED"
    except Exception:
        details["continuous_report_status"] = "UNAVAILABLE"
        if status != "BLOCKED":
            status = "DEGRADED"

    evidence = _find_latest_spec040_evidence()
    if evidence:
        try:
            details["latest_evidence_spec040"] = _format_evidence_payload(evidence)
            evidence_status = _map_gate_status_to_envelope_status(
                evidence.get("gate_status", "UNKNOWN")
            )
            details["evidence_spec_040_latest_status"] = evidence_status
            if evidence_status == "BLOCKED":
                status = "BLOCKED"
            elif evidence_status in ("DEGRADED", "UNAVAILABLE"):
                if status != "BLOCKED":
                    status = "DEGRADED"
        except Exception as exc:
            logger.warning(f"Failed to format latest spec-040 evidence: {exc}")
            details["latest_evidence_spec040"] = None
            if status != "BLOCKED":
                status = "DEGRADED"
    else:
        if status != "BLOCKED":
            status = "DEGRADED"

    return OpsEnvelope(
        status=status,
        details=details,
    )


@router.get("/shadow-report", response_model=OpsEnvelope)
async def ops_shadow_report() -> OpsEnvelope:
    raise HTTPException(status_code=503, detail="Shadow report source cannot be produced safely")


@router.get("/continuous-report", response_model=OpsEnvelope)
async def ops_continuous_report() -> OpsEnvelope:
    try:
        report = await get_continuous_report()
        report_dict = report.model_dump(mode="json")
        status = _map_continuous_report_status(report.report_status)
        return OpsEnvelope(status=status, details=report_dict)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to get continuous report: {e}")
        raise HTTPException(status_code=503, detail="Continuous report unavailable")


@router.get("/evidence/spec-040/latest", response_model=OpsEnvelope)
async def ops_evidence_spec040_latest() -> OpsEnvelope:
    evidence = _find_latest_spec040_evidence()
    if not evidence:
        raise HTTPException(
            status_code=503, detail="Latest spec-040 evidence not found or malformed"
        )

    required_keys = ["continuous_report", "gate_status", "generated_at"]
    for key in required_keys:
        if key not in evidence:
            raise HTTPException(status_code=503, detail=f"Malformed evidence: missing '{key}'")

    report = evidence.get("continuous_report", {})
    if report.get("positions_closed") is None or report.get("feedback_persisted") is None:
        raise HTTPException(
            status_code=503, detail="Malformed evidence: incomplete lifecycle counters"
        )

    formatted_payload = _format_evidence_payload(evidence)
    envelope_status = _map_gate_status_to_envelope_status(evidence.get("gate_status", "UNKNOWN"))

    return OpsEnvelope(status=envelope_status, details=formatted_payload)


@router.get("/backfill-status", response_model=OpsEnvelope)
async def ops_backfill_status() -> OpsEnvelope:
    return OpsEnvelope(
        status="UNAVAILABLE", details={"message": "Backfill not configured or non-applicable"}
    )
