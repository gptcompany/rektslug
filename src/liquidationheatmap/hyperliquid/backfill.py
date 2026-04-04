"""Historical backfill coordinator and schema for Hyperliquid expert snapshots."""

from dataclasses import dataclass
from typing import Any


@dataclass
class BackfillBatchRecord:
    batch_id: str
    interval: str
    symbols: list[str]
    experts: list[str]
    start_ts: str
    end_ts: str
    coverage: dict[str, dict[str, int]]
    timeline_policy: str
    input_identity: dict[str, Any]


def build_backfill_batch(
    batch_id: str,
    interval: str,
    symbols: list[str],
    experts: list[str],
    start_ts: str,
    end_ts: str,
    coverage: dict[str, dict[str, int]],
    timeline_policy: str,
    input_identity: dict[str, Any],
) -> BackfillBatchRecord:
    """Build a deterministic backfill batch record."""
    return BackfillBatchRecord(
        batch_id=batch_id,
        interval=interval,
        symbols=list(symbols),
        experts=list(experts),
        start_ts=start_ts,
        end_ts=end_ts,
        coverage=dict(coverage),
        timeline_policy=timeline_policy,
        input_identity=dict(input_identity),
    )


def categorize_backfill_missing(source_exists: bool, decode_success: bool) -> str:
    """
    Determine if a missing timestamp is a 'gap' (no source data)
    or a 'failure' (data present, but not processable).
    """
    if not source_exists:
        return "gap"
    if not decode_success:
        return "failure"
    return "success"
