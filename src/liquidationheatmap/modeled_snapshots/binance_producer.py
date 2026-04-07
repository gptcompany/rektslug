"""Binance modeled-snapshot producer."""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.liquidationheatmap.contracts.aggregation import aggregate_to_bucket_grid
from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.modeled_snapshots.export_layout import (
    build_manifest,
    write_manifest,
    write_modeled_artifact,
)
from src.liquidationheatmap.modeled_snapshots.snapshot_schema import (
    validate_artifact,
    validate_iso8601_z_timestamp,
)
from src.liquidationheatmap.models.binance_standard import BinanceStandardModel

logger = logging.getLogger(__name__)

class BinanceProducer:
    """Producer for Binance modeled snapshots."""

    def __init__(self, base_dir: Path | str, db_path: Optional[str] = None):
        self.base_dir = Path(base_dir)
        self.db_service = DuckDBService(db_path=db_path, read_only=True)
        self.model = BinanceStandardModel()

    def export_snapshot(
        self, 
        symbol: str, 
        snapshot_ts: str,
        bin_size: float = 100.0,
        lookback_days: int = 30
    ) -> Any:
        """Produce and write a Binance modeled snapshot (artifact + manifest)."""
        snapshot_ts = validate_iso8601_z_timestamp("snapshot_ts", snapshot_ts)
        
        # Step 1: Collect inputs for binance_standard
        try:
            inputs, input_identity, status = self._collect_inputs(symbol, snapshot_ts, lookback_days)
            
            # If we don't have enough data to even try a partial, we fail
            if status == "blocked_source_missing":
                manifest = build_manifest("binance", snapshot_ts, [], {"binance_standard": {"status": status, "reason": "Missing critical inputs"}})
                write_manifest(self.base_dir, "binance", symbol, manifest)
                return manifest

            # Step 2: Run model
            levels = self.model.calculate_liquidations(
                current_price=inputs["current_price"],
                open_interest=inputs["open_interest"],
                symbol=symbol,
                large_trades=inputs["large_trades"]
            )
            
            # Step 3: Aggregate
            grid, long_dist, short_dist = aggregate_to_bucket_grid(levels, bin_size)
            
            # Step 4: Prepare artifact
            run_id = f"run_{int(datetime.now(timezone.utc).timestamp())}"
            run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            
            artifact_payload = {
                "exchange": "binance",
                "model_id": "binance_standard",
                "symbol": symbol,
                "snapshot_ts": snapshot_ts,
                "reference_price": float(inputs["current_price"]),
                "bucket_grid": {
                    "min_price": float(grid.min_price) if grid.min_price is not None else None,
                    "max_price": float(grid.max_price) if grid.max_price is not None else None,
                    "step": float(grid.step) if grid.step is not None else None
                },
                "long_distribution": {k: float(v) for k, v in long_dist.items()},
                "short_distribution": {k: float(v) for k, v in short_dist.items()},
                "source_metadata": {
                    "input_identity": input_identity
                },
                "generation_metadata": {
                    "run_id": run_id,
                    "run_reason": "scheduled_export",
                    "run_ts": run_ts,
                    "producer_version": "1.0.0"
                }
            }
            
            # Validate
            artifact = validate_artifact(artifact_payload)
            
            # Write artifact
            write_modeled_artifact(
                self.base_dir, "binance", symbol, snapshot_ts, "binance_standard", artifact_payload
            )
            
            # Build and write manifest
            # If status is partial, it will be reflected in manifest
            failures = {}
            if status == "partial":
                 failures = {"binance_standard": {"status": "partial", "reason": "Missing some inputs, using fallbacks"}}
                 manifest = build_manifest("binance", snapshot_ts, [artifact], failures)
            else:
                 manifest = build_manifest("binance", snapshot_ts, [artifact])
                 
            write_manifest(self.base_dir, "binance", symbol, manifest)
            
            return manifest

        except Exception as e:
            logger.exception(f"Failed to produce Binance snapshot for {snapshot_ts}")
            # Write a partial or failed manifest
            failure_info = {
                "status": "failed_processing",
                "reason": str(e)
            }
            manifest = build_manifest("binance", snapshot_ts, [], {"binance_standard": failure_info})
            write_manifest(self.base_dir, "binance", symbol, manifest)
            return manifest

    def _collect_inputs(
        self, 
        symbol: str, 
        snapshot_ts: str, 
        lookback_days: int
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
        """Collect pinned inputs from DuckDB."""
        status = "available"
        input_identity = {}
        inputs = {}
        
        # 1. Get current price at or before snapshot_ts
        kline_table = self.db_service._kline_table_for_interval("1m")
        
        price_row = self.db_service.conn.execute(
            f"""
            SELECT close, open_time
            FROM {kline_table}
            WHERE symbol = ? AND open_time <= ?
            ORDER BY open_time DESC
            LIMIT 1
            """,
            [symbol, snapshot_ts]
        ).fetchone()
        
        if not price_row:
            # Critical missing
            return {}, {}, "blocked_source_missing"
            
        current_price = Decimal(str(price_row[0]))
        price_ts = price_row[1].strftime("%Y-%m-%dT%H:%M:%SZ")
        input_identity["current_price"] = {
            "source": kline_table,
            "timestamp": price_ts,
            "value": float(current_price)
        }
        inputs["current_price"] = current_price
        
        # 2. Get OI at or before snapshot_ts
        oi_row = self.db_service.conn.execute(
            """
            SELECT open_interest_value, timestamp
            FROM open_interest_history
            WHERE symbol = ? AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [symbol, snapshot_ts]
        ).fetchone()
        
        if not oi_row:
            # We can't really function without OI for standard model
            # but maybe we fallback?
            # For now, let's mark it partial and use a fallback if we want, 
            # but let's see what spec says. 
            # "Missing required source input MUST produce partial status"
            status = "partial"
            # Fallback OI logic from liquidations.py
            open_interest = Decimal(float(current_price)) * Decimal("100")
            open_interest = max(open_interest, Decimal("500000"))
            input_identity["open_interest"] = {
                "source": "fallback",
                "value": float(open_interest),
                "reason": "No OI found in DB"
            }
        else:
            open_interest = Decimal(str(oi_row[0]))
            oi_ts = oi_row[1].strftime("%Y-%m-%dT%H:%M:%SZ")
            input_identity["open_interest"] = {
                "source": "open_interest_history",
                "timestamp": oi_ts,
                "value": float(open_interest)
            }
        
        inputs["open_interest"] = open_interest
        
        # 3. Get large trades within lookback window ending at snapshot_ts
        dt_snapshot = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
        start_ts = (dt_snapshot - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Use aggtrades_history table
        try:
            trades_df = self.db_service.conn.execute(
                """
                SELECT timestamp, price, quantity, side, gross_value
                FROM aggtrades_history
                WHERE symbol = ? AND exchange = 'binance' AND timestamp >= ? AND timestamp <= ?
                AND gross_value >= 500000
                """,
                [symbol, start_ts, snapshot_ts]
            ).df()
            
            if trades_df.empty:
                # Not necessarily partial, just no large trades found. 
                # But if the table itself is empty, maybe it's partial.
                pass
                
            input_identity["large_trades"] = {
                "source": "aggtrades_history",
                "start_ts": start_ts,
                "end_ts": snapshot_ts,
                "count": len(trades_df)
            }
            inputs["large_trades"] = trades_df
        except Exception as e:
            logger.warning(f"Failed to query aggtrades_history: {e}")
            status = "partial"
            input_identity["large_trades"] = {
                "source": "missing",
                "reason": str(e)
            }
            inputs["large_trades"] = None

        return inputs, input_identity, status
