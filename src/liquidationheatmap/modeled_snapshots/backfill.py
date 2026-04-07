"""Historical backfill coordinator and schema for modeled snapshots."""

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.liquidationheatmap.modeled_snapshots.snapshot_schema import validate_iso8601_z_timestamp
from src.liquidationheatmap.modeled_snapshots.export_layout import write_backfill_batch_record

logger = logging.getLogger(__name__)

@dataclass
class BackfillBatchRecord:
    batch_id: str
    exchange: str
    interval: str
    symbols: List[str]
    models: List[str]
    start_ts: str
    end_ts: str
    coverage: Dict[str, Dict[str, Any]] # symbol -> {status -> count}
    timeline_policy: str
    input_identity: Dict[str, Any]
    generation_metadata: Dict[str, Any]

class BackfillCoordinator:
    """Coordinates deterministic backfills across symbols and time ranges."""

    def __init__(self, producer: Any):
        self.producer = producer

    def run_backfill(
        self,
        exchange: str,
        symbol: str,
        start_ts: str,
        end_ts: str,
        step_minutes: int = 60,
        models: Optional[List[str]] = None,
        batch_id: Optional[str] = None
    ) -> BackfillBatchRecord:
        """Run backfill for a given range and symbol."""
        validate_iso8601_z_timestamp("start_ts", start_ts)
        validate_iso8601_z_timestamp("end_ts", end_ts)
        
        start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        
        batch_id = batch_id or f"backfill_{exchange}_{symbol}_{int(time.time())}"
        models = models or ["binance_standard", "binance_depth_weighted"]
        
        current_dt = start_dt
        coverage = {"success": 0, "partial": 0, "gap": 0, "failure": 0}
        
        all_input_identities = []
        
        start_time_perf = time.perf_counter()
        
        while current_dt <= end_dt:
            snapshot_ts = current_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            logger.info(f"Backfilling {exchange} {symbol} at {snapshot_ts}")
            
            manifest = self.producer.export_snapshot(
                symbol=symbol,
                snapshot_ts=snapshot_ts,
                channels=models
            )
            
            # Aggregate status for the batch record
            statuses = [m.availability_status for m in manifest.models.values()]
            if all(s == "available" for s in statuses):
                coverage["success"] += 1
            elif any(s == "partial" for s in statuses):
                coverage["partial"] += 1
            elif any(s.startswith("blocked") for s in statuses):
                coverage["gap"] += 1
            else:
                coverage["failure"] += 1
                
            # Collect input identities for provenance
            for mid, m_entry in manifest.models.items():
                if m_entry.availability_status in ("available", "partial"):
                    all_input_identities.append({
                        "snapshot_ts": snapshot_ts,
                        "model_id": mid,
                        "input_identity": m_entry.source_metadata.get("input_identity")
                    })
            
            current_dt += timedelta(minutes=step_minutes)
            
        end_time_perf = time.perf_counter()
        duration = end_time_perf - start_time_perf
        
        record = BackfillBatchRecord(
            batch_id=batch_id,
            exchange=exchange,
            interval=f"{step_minutes}m",
            symbols=[symbol],
            models=models,
            start_ts=start_ts,
            end_ts=end_ts,
            coverage={symbol: coverage},
            timeline_policy="fixed_step",
            input_identity={"samples": all_input_identities[:100]}, # Sample for size
            generation_metadata={
                "duration_seconds": duration,
                "run_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        )
        
        write_backfill_batch_record(self.producer.base_dir, batch_id, asdict(record))
        
        return record
