"""Bybit modeled-snapshot producer."""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.liquidationheatmap.modeled_snapshots.export_layout import (
    build_manifest,
    write_manifest,
    write_modeled_artifact,
)
from src.liquidationheatmap.modeled_snapshots.snapshot_schema import (
    validate_iso8601_z_timestamp,
)
from src.liquidationheatmap.modeled_snapshots.bybit_readiness import BybitReadinessGate

logger = logging.getLogger(__name__)

class BybitProducer:
    """Producer for Bybit modeled snapshots."""

    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)
        self.readiness_gate = BybitReadinessGate()

    def export_snapshot(
        self, 
        symbol: str, 
        snapshot_ts: str,
        channels: Optional[List[str]] = None
    ) -> Any:
        """Produce and write Bybit modeled snapshots (artifacts + manifest)."""
        snapshot_ts = validate_iso8601_z_timestamp("snapshot_ts", snapshot_ts)
        channels = channels or ["bybit_standard", "depth_weighted"]
        
        artifacts = []
        failures = {}

        for channel in channels:
            # Step 1: Check readiness
            report = self.readiness_gate.check_readiness(symbol, snapshot_ts, channel)
            
            if report.status != "available":
                failures[channel] = {
                    "status": report.status,
                    "reason": "Source readiness check failed",
                    "details": report.details
                }
                continue

            # Step 2: Implementation for available state (Phase 5)
            # For now, we treat everything else as blocked until Phase 5
            failures[channel] = {
                "status": "blocked_source_unverified",
                "reason": "Export implementation pending Phase 5",
                "details": report.details
            }

        # Build and write manifest
        manifest = build_manifest("bybit", snapshot_ts, artifacts, failures)
        write_manifest(self.base_dir, "bybit", symbol, manifest)
        
        return manifest
