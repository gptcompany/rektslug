"""Producer run metadata and scheduling semantics for Hyperliquid expert snapshots."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        def __str__(self) -> str:
            return str(self.value)


class RunKind(StrEnum):
    """Accepted producer run kinds."""

    BASELINE = "baseline"
    EXTRA = "extra"
    MANUAL = "manual"
    BACKFILL = "backfill"


@dataclass
class ProducerRunMetadata:
    run_id: str
    run_reason: str
    run_ts: str
    last_actual_run_ts: str
    producer_version: str


def build_run_metadata(
    run_reason: RunKind | str, run_ts: str, last_actual_run_ts: str, producer_version: str = "1.0.0"
) -> ProducerRunMetadata:
    """Build a compliant ProducerRunMetadata record."""
    return ProducerRunMetadata(
        run_id=str(uuid.uuid4()),
        run_reason=str(run_reason),
        run_ts=run_ts,
        last_actual_run_ts=last_actual_run_ts,
        producer_version=producer_version,
    )


def calculate_next_baseline(last_actual_run_ts: datetime, cadence_minutes: int) -> datetime:
    """
    Calculate the next baseline target based on the agreed scheduling semantics:
    cadence is measured from the last actual run timestamp.
    An extra run re-anchors the baseline schedule.
    """
    return last_actual_run_ts + timedelta(minutes=cadence_minutes)
