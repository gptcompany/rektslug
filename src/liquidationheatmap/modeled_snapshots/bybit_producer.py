"""Bybit modeled-snapshot producer."""

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
from src.liquidationheatmap.modeled_snapshots.bybit_readiness import BybitReadinessGate
from src.liquidationheatmap.models.binance_standard import BinanceStandardModel
from src.liquidationheatmap.models.binance_depth_weighted import BinanceDepthWeightedModel

logger = logging.getLogger(__name__)

class BybitProducer:
    """Producer for Bybit modeled snapshots."""

    # Bybit BTCUSDT MMR tiers (2026 audit)
    BYBIT_MMR_TIERS = [
        (Decimal("2000000"), Decimal("0.005"), Decimal("0")),
        (Decimal("2600000"), Decimal("0.0056"), Decimal("0")),
        (Decimal("3200000"), Decimal("0.0062"), Decimal("0")),
        (Decimal("3800000"), Decimal("0.0068"), Decimal("0")),
        (Decimal("4400000"), Decimal("0.0074"), Decimal("0")),
        (Decimal("5000000"), Decimal("0.008"), Decimal("0")),
    ]

    CATALOG_ROOT = Path("/media/sam/1TB/ccxt-data-pipeline/data/catalog")

    def __init__(self, base_dir: Path | str, db_path: Optional[str] = None):
        self.base_dir = Path(base_dir)
        self.db_service = DuckDBService(db_path=db_path, read_only=True)
        self.readiness_gate = BybitReadinessGate()
        self.standard_model = BinanceStandardModel(mmr_tiers=self.BYBIT_MMR_TIERS)
        self.depth_weighted_model = BinanceDepthWeightedModel(mmr_tiers=self.BYBIT_MMR_TIERS)

    def export_snapshot(
        self, 
        symbol: str, 
        snapshot_ts: str,
        bin_size: float = 100.0,
        lookback_days: int = 30,
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

            # Step 2: Collect inputs
            try:
                if channel == "bybit_standard":
                    model = self.standard_model
                elif channel == "depth_weighted":
                    model = self.depth_weighted_model
                else:
                    failures[channel] = {"status": "unsupported", "reason": f"Unknown channel: {channel}"}
                    continue

                inputs, input_identity, status = self._collect_inputs(symbol, snapshot_ts, lookback_days, channel)
                
                if status.startswith("blocked"):
                    failures[channel] = {"status": status, "reason": "Input collection failed", "details": input_identity}
                    continue

                # Step 3: Run model
                levels = model.calculate_liquidations(
                    current_price=inputs["current_price"],
                    open_interest=inputs["open_interest"],
                    symbol=symbol,
                    large_trades=inputs["large_trades"],
                    orderbook=inputs.get("orderbook")
                )
                
                # Step 4: Aggregate
                grid, long_dist, short_dist = aggregate_to_bucket_grid(levels, bin_size)
                
                # Step 5: Prepare artifact
                run_id = f"run_{int(datetime.now(timezone.utc).timestamp())}"
                run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                
                artifact_payload = {
                    "exchange": "bybit",
                    "model_id": channel,
                    "symbol": symbol,
                    "snapshot_ts": snapshot_ts,
                    "reference_price": float(inputs["current_price"]),
                    "bucket_grid": {
                        "min_price": float(grid.min_price) if grid.min_price is not None else None,
                        "max_price": float(grid.max_price) if grid.max_price is not None else None,
                        "step": float(grid.step) if grid.step is not None else None,
                        "price_levels": grid.price_levels
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
                
                artifact_obj = validate_artifact(artifact_payload)
                artifacts.append(artifact_obj)
                
                write_modeled_artifact(
                    self.base_dir, "bybit", symbol, snapshot_ts, channel, artifact_payload
                )
                
                if status == "partial":
                    failures[channel] = {"status": "partial", "reason": "Input collection was partial", "details": input_identity}

            except Exception as e:
                logger.exception(f"Failed to produce Bybit {channel} snapshot")
                failures[channel] = {"status": "failed_processing", "reason": str(e)}

        # Build and write manifest
        manifest = build_manifest("bybit", snapshot_ts, artifacts, failures)
        write_manifest(self.base_dir, "bybit", symbol, manifest)
        
        return manifest

    def _collect_inputs(self, symbol: str, snapshot_ts: str, lookback_days: int, channel: str) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
        """Collect pinned inputs for Bybit from Parquet catalog."""
        dt = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
        parquet_symbol = f"{symbol}-PERP.BYBIT"
        
        status = "available"
        input_identity = {}
        inputs = {}
        
        # 1. Current Price (from ohlcv Parquet)
        ohlcv_path = self.CATALOG_ROOT / "ohlcv" / parquet_symbol / f"{date_str}.parquet"
        if not ohlcv_path.exists():
            return {}, {}, "blocked_source_missing"
            
        try:
            price_row = self.db_service.conn.execute(f"""
                SELECT close, timestamp FROM read_parquet('{ohlcv_path}')
                WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1
            """, [snapshot_ts]).fetchone()
            
            if not price_row:
                return {}, {}, "blocked_source_missing"
                
            current_price = Decimal(str(price_row[0]))
            inputs["current_price"] = current_price
            input_identity["current_price"] = {"source": str(ohlcv_path), "timestamp": price_row[1].strftime("%Y-%m-%dT%H:%M:%SZ")}
        except Exception as e:
            logger.warning(f"Failed to read ohlcv parquet {ohlcv_path}: {e}")
            return {}, {}, "blocked_source_missing"
        
        # 2. Open Interest
        oi_path = self.CATALOG_ROOT / "open_interest" / parquet_symbol / f"{date_str}.parquet"
        if oi_path.exists():
            try:
                oi_row = self.db_service.conn.execute(f"""
                    SELECT open_interest_value, timestamp FROM read_parquet('{oi_path}')
                    WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1
                """, [snapshot_ts]).fetchone()
                if oi_row:
                    inputs["open_interest"] = Decimal(str(oi_row[0]))
                    input_identity["open_interest"] = {"source": str(oi_path), "timestamp": oi_row[1].strftime("%Y-%m-%dT%H:%M:%SZ")}
                else:
                    status = "partial"
                    inputs["open_interest"] = current_price * Decimal("100") # fallback
            except Exception:
                status = "partial"
                inputs["open_interest"] = current_price * Decimal("100")
        else:
            status = "partial"
            inputs["open_interest"] = current_price * Decimal("100")
            
        # 3. Trades
        trades_path = self.CATALOG_ROOT / "trades" / parquet_symbol / f"{date_str}.parquet"
        if trades_path.exists():
            try:
                trades_df = self.db_service.conn.execute(f"""
                    SELECT timestamp, price, quantity, side, value as gross_value 
                    FROM read_parquet('{trades_path}')
                    WHERE timestamp <= ? AND value >= 500000
                    ORDER BY timestamp DESC
                """, [snapshot_ts]).df()
                inputs["large_trades"] = trades_df
                input_identity["large_trades"] = {"source": str(trades_path), "count": len(trades_df)}
            except Exception:
                inputs["large_trades"] = None
                input_identity["large_trades"] = {"source": "error"}
        else:
            inputs["large_trades"] = None
            input_identity["large_trades"] = {"source": "missing"}
            
        # 4. Orderbook
        if channel == "depth_weighted":
            ob_path = self.CATALOG_ROOT / "orderbook" / parquet_symbol / f"{date_str}.parquet"
            if ob_path.exists():
                try:
                    ob_row = self.db_service.conn.execute(f"""
                        SELECT * FROM read_parquet('{ob_path}')
                        WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1
                    """, [snapshot_ts]).fetchone()
                    if ob_row:
                        bids = []
                        asks = []
                        for i in range(20):
                            base_idx = 4 + i * 4
                            bids.append((ob_row[base_idx], ob_row[base_idx+1]))
                            asks.append((ob_row[base_idx+2], ob_row[base_idx+3]))
                        inputs["orderbook"] = {'bids': bids, 'asks': asks}
                        input_identity["orderbook"] = {"source": str(ob_path), "timestamp": ob_row[0].strftime("%Y-%m-%dT%H:%M:%SZ")}
                    else:
                        return {}, {}, "blocked_source_missing"
                except Exception:
                    return {}, {}, "blocked_source_missing"
            else:
                return {}, {}, "blocked_source_missing"

        return inputs, input_identity, status
