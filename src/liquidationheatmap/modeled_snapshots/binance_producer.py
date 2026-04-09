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
from src.liquidationheatmap.models.binance_depth_weighted import BinanceDepthWeightedModel

logger = logging.getLogger(__name__)


def _normalize_utc_datetime(value: Any) -> datetime:
    """Normalize DuckDB / pandas timestamp values into UTC-aware datetimes."""
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        raise TypeError(f"Expected datetime-compatible value, got {type(value)!r}")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_utc_z(value: Any) -> str:
    """Format timestamps as canonical UTC Z strings."""
    return _normalize_utc_datetime(value).strftime("%Y-%m-%dT%H:%M:%SZ")


class BinanceProducer:
    """Producer for Binance modeled snapshots."""
    MAX_CURRENT_PRICE_AGE = timedelta(hours=2)
    MAX_OPEN_INTEREST_AGE = timedelta(hours=24)

    def __init__(self, base_dir: Path | str, db_path: Optional[str] = None):
        self.base_dir = Path(base_dir)
        self.db_service = DuckDBService(db_path=db_path, read_only=True)
        self.standard_model = BinanceStandardModel()
        self.depth_weighted_model = BinanceDepthWeightedModel()

    def _artifact_path(self, symbol: str, snapshot_ts: str, model_id: str) -> Path:
        return self.base_dir / "binance" / "artifacts" / symbol / snapshot_ts / f"{model_id}.json"

    def _remove_artifact_if_exists(self, symbol: str, snapshot_ts: str, model_id: str) -> None:
        artifact_path = self._artifact_path(symbol, snapshot_ts, model_id)
        if artifact_path.exists():
            artifact_path.unlink()

    def export_snapshot(
        self, 
        symbol: str, 
        snapshot_ts: str,
        bin_size: float = 100.0,
        lookback_days: int = 30,
        channels: Optional[List[str]] = None
    ) -> Any:
        """Produce and write Binance modeled snapshots (artifacts + manifest)."""
        snapshot_ts = validate_iso8601_z_timestamp("snapshot_ts", snapshot_ts)
        # Default channels
        channels = channels or ["binance_standard", "binance_depth_weighted"]
        
        # Step 1: Collect common inputs
        try:
            inputs, input_identity, base_status = self._collect_inputs(symbol, snapshot_ts, lookback_days)
            
            if base_status == "blocked_source_missing":
                failures = {}
                for channel in channels:
                    self._remove_artifact_if_exists(symbol, snapshot_ts, channel)
                    failures[channel] = {
                        "status": base_status,
                        "reason": "Critical input collection failed",
                        "details": input_identity,
                    }
                manifest = build_manifest("binance", snapshot_ts, [], failures)
                write_manifest(self.base_dir, "binance", symbol, manifest)
                return manifest

            artifacts = []
            failures = {}

            # Step 2: Handle each channel
            for channel in channels:
                try:
                    # Reset input identity for each channel if we add more
                    current_input_identity = input_identity.copy()
                    channel_status = base_status
                    
                    if channel == "binance_standard":
                        model = self.standard_model
                        extra_inputs = {}
                    elif channel == "binance_depth_weighted":
                        model = self.depth_weighted_model
                        orderbook, ob_identity, ob_status = self._collect_orderbook(symbol, snapshot_ts)
                        extra_inputs = {"orderbook": orderbook}
                        current_input_identity["orderbook"] = ob_identity
                        if ob_status != "available":
                            channel_status = ob_status
                    else:
                        failures[channel] = {"status": "unsupported", "reason": f"Unknown channel: {channel}"}
                        continue

                    # If channel is blocked, skip artifact production
                    if channel_status.startswith("blocked"):
                        self._remove_artifact_if_exists(symbol, snapshot_ts, channel)
                        failures[channel] = {
                            "status": channel_status,
                            "reason": "Missing required source data",
                            "details": current_input_identity,
                        }
                        continue

                    levels = model.calculate_liquidations(
                        current_price=inputs["current_price"],
                        open_interest=inputs["open_interest"],
                        symbol=symbol,
                        large_trades=inputs["large_trades"],
                        **extra_inputs
                    )
                    
                    grid, long_dist, short_dist = aggregate_to_bucket_grid(levels, bin_size)
                    if not long_dist and not short_dist:
                        self._remove_artifact_if_exists(symbol, snapshot_ts, channel)
                        failures[channel] = {
                            "status": "failed_processing",
                            "reason": "Model produced empty distributions",
                            "details": {"input_identity": current_input_identity},
                        }
                        continue
                    
                    run_id = f"run_{int(datetime.now(timezone.utc).timestamp())}"
                    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    
                    artifact_payload = {
                        "exchange": "binance",
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
                            "input_identity": current_input_identity
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
                        self.base_dir, "binance", symbol, snapshot_ts, channel, artifact_payload
                    )

                    if channel_status == "partial":
                        failures[channel] = {
                            "status": "partial",
                            "reason": "Input collection was partial",
                            "details": current_input_identity,
                        }

                except Exception as e:
                    self._remove_artifact_if_exists(symbol, snapshot_ts, channel)
                    logger.exception(f"Failed to produce Binance {channel} snapshot")
                    failures[channel] = {"status": "failed_processing", "reason": str(e)}

            # Build and write manifest
            manifest = build_manifest("binance", snapshot_ts, artifacts, failures)
            write_manifest(self.base_dir, "binance", symbol, manifest)
            
            return manifest

        except Exception as e:
            logger.exception(f"Failed to produce Binance snapshots for {snapshot_ts}")
            failures = {c: {"status": "failed_processing", "reason": str(e)} for c in channels}
            manifest = build_manifest("binance", snapshot_ts, [], failures)
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
        snapshot_dt = _normalize_utc_datetime(
            datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
        )
        
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
            return {}, {}, "blocked_source_missing"
            
        current_price = Decimal(str(price_row[0]))
        price_dt = _normalize_utc_datetime(price_row[1])
        price_age = snapshot_dt - price_dt
        input_identity["current_price"] = {
            "source": kline_table,
            "timestamp": _format_utc_z(price_row[1]),
            "age_seconds": int(price_age.total_seconds()),
            "value": float(current_price)
        }
        if price_age > self.MAX_CURRENT_PRICE_AGE:
            input_identity["current_price"]["status"] = "stale"
            input_identity["current_price"]["max_age_seconds"] = int(
                self.MAX_CURRENT_PRICE_AGE.total_seconds()
            )
            input_identity["current_price"]["reason"] = (
                "No sufficiently fresh current price anchor for snapshot_ts"
            )
            return {}, input_identity, "blocked_source_missing"
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
            status = "partial"
            open_interest = Decimal(float(current_price)) * Decimal("100")
            open_interest = max(open_interest, Decimal("500000"))
            input_identity["open_interest"] = {
                "source": "fallback",
                "value": float(open_interest),
                "reason": "No OI found in DB"
            }
        else:
            open_interest = Decimal(str(oi_row[0]))
            oi_dt = _normalize_utc_datetime(oi_row[1])
            oi_age = snapshot_dt - oi_dt
            input_identity["open_interest"] = {
                "source": "open_interest_history",
                "timestamp": _format_utc_z(oi_row[1]),
                "age_seconds": int(oi_age.total_seconds()),
                "value": float(open_interest)
            }
            if oi_age > self.MAX_OPEN_INTEREST_AGE:
                status = "partial"
                input_identity["open_interest"]["status"] = "stale"
                input_identity["open_interest"]["max_age_seconds"] = int(
                    self.MAX_OPEN_INTEREST_AGE.total_seconds()
                )
                input_identity["open_interest"]["reason"] = (
                    "Open interest anchor is stale for snapshot_ts"
                )
        
        inputs["open_interest"] = open_interest
        
        # 3. Get large trades within lookback window ending at snapshot_ts
        dt_snapshot = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
        start_ts = (dt_snapshot - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
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

    def _collect_orderbook(self, symbol: str, snapshot_ts: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], str]:
        """Fetch orderbook snapshot from Parquet."""
        dt = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
        
        parquet_symbol = f"{symbol}-PERP.BINANCE"
        orderbook_symbol = f"{symbol}-PERP"
        parquet_path = f"/media/sam/1TB/ccxt-data-pipeline/data/catalog/orderbook/{parquet_symbol}/{date_str}.parquet"
        
        if not Path(parquet_path).exists():
            return None, {"source": parquet_path, "status": "missing"}, "blocked_source_missing"
            
        try:
            ob_row = self.db_service.conn.execute(f"""
                SELECT * FROM read_parquet('{parquet_path}')
                WHERE symbol = ? AND timestamp <= ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, [orderbook_symbol, snapshot_ts]).fetchone()
            
            if not ob_row:
                 return None, {"source": parquet_path, "status": "no_snapshot_before_ts"}, "blocked_source_missing"
            
            bids = []
            asks = []
            # Indices for DuckDB result from Parquet:
            # 0: timestamp, 1: symbol, 2: venue, 3: sequence
            # 4: bid_price_0, 5: bid_qty_0, 6: ask_price_0, 7: ask_qty_0
            for i in range(20):
                base_idx = 4 + i * 4
                bids.append((ob_row[base_idx], ob_row[base_idx+1]))
                asks.append((ob_row[base_idx+2], ob_row[base_idx+3]))
                
            orderbook = {'bids': bids, 'asks': asks}
            identity = {
                "source": parquet_path,
                "timestamp": _format_utc_z(ob_row[0]),
                "status": "available"
            }
            return orderbook, identity, "available"
            
        except Exception as e:
            logger.warning(f"Failed to read orderbook parquet {parquet_path}: {e}")
            return None, {"source": parquet_path, "status": "error", "error": str(e)}, "blocked_source_missing"
