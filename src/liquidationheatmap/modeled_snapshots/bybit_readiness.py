"""Bybit source readiness gate."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class ReadinessRequirement:
    input_class: str
    paths: List[str]
    required: bool

@dataclass
class ReadinessReport:
    exchange: str
    snapshot_ts: str
    channel: str
    status: str
    details: Dict[str, Any]

class BybitReadinessGate:
    """Checks if Bybit source data is available for a given window."""

    CATALOG_ROOT = Path("/media/sam/1TB/ccxt-data-pipeline/data/catalog")
    HISTORICAL_ROOT = Path("/media/sam/3TB-WDC/bybit_data_downloader/data/historical")
    METRICS_ROOT = Path("/media/sam/3TB-WDC/bybit_data_downloader/data/market_metrics")

    # Gap: Bybit orderbook not continuous between 2025-08-21 and 2026-04-05
    ORDERBOOK_GAP_START = datetime(2025, 8, 21, tzinfo=timezone.utc)
    ORDERBOOK_GAP_END = datetime(2026, 4, 5, tzinfo=timezone.utc)

    def check_readiness(
        self, 
        symbol: str, 
        snapshot_ts: str, 
        channel: str
    ) -> ReadinessReport:
        """Check readiness for Bybit artifact export."""
        dt = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
        
        # Define requirements per channel
        requirements = []
        
        # Base requirements for bybit_standard
        # 1. Klines (OHLCV)
        requirements.append(ReadinessRequirement(
            "klines",
            [
                str(self.CATALOG_ROOT / "ohlcv" / f"{symbol}-PERP.BYBIT"),
            ],
            True
        ))
        
        # 2. Open Interest
        requirements.append(ReadinessRequirement(
            "open_interest",
            [
                str(self.CATALOG_ROOT / "open_interest" / f"{symbol}-PERP.BYBIT"),
                str(self.METRICS_ROOT / "open_interest")
            ],
            True
        ))
        
        # 3. Funding
        requirements.append(ReadinessRequirement(
            "funding",
            [
                str(self.CATALOG_ROOT / "funding_rate" / f"{symbol}-PERP.BYBIT"),
                str(self.METRICS_ROOT / "funding_rates")
            ],
            True
        ))
        
        # 4. Trades
        requirements.append(ReadinessRequirement(
            "trades",
            [
                str(self.CATALOG_ROOT / "trades" / f"{symbol}-PERP.BYBIT"),
                str(self.HISTORICAL_ROOT / "trade" / "contract" / symbol)
            ],
            True
        ))
        
        if channel == "depth_weighted":
            # 5. Orderbook
            requirements.append(ReadinessRequirement(
                "orderbook",
                [
                    str(self.CATALOG_ROOT / "orderbook" / f"{symbol}-PERP.BYBIT"),
                    str(self.HISTORICAL_ROOT / "orderbook" / "contract" / symbol)
                ],
                True
            ))

        details = {}
        status = "available"
        
        for req in requirements:
            found = False
            found_path = None
            for p in req.paths:
                if Path(p).exists():
                    found = True
                    found_path = p
                    break
            
            details[req.input_class] = {
                "present": found,
                "path": found_path if found else req.paths[0],
                "required": req.required
            }
            
            if not found and req.required:
                status = "blocked_source_missing"

        # Special gap check for orderbook
        if channel == "depth_weighted":
            if self.ORDERBOOK_GAP_START <= dt <= self.ORDERBOOK_GAP_END:
                status = "blocked_source_missing"
                if "orderbook" not in details:
                     details["orderbook"] = {"present": False, "required": True}
                details["orderbook"]["status"] = "in_gap"
                details["orderbook"]["reason"] = "Orderbook gap 2025-08-21 to 2026-04-05"

        return ReadinessReport(
            exchange="bybit",
            snapshot_ts=snapshot_ts,
            channel=channel,
            status=status,
            details=details
        )
