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
    NORMALIZED_ROOT = Path("/media/sam/1TB/rektslug/data/historical_normalized/bybit")

    # Gap: Bybit orderbook is not continuous between historical 3TB-WDC files and
    # the live ccxt-data-pipeline catalog. End is exclusive.
    ORDERBOOK_GAP_START = datetime(2025, 8, 21, tzinfo=timezone.utc)
    ORDERBOOK_GAP_END_EXCLUSIVE = datetime(2026, 4, 6, tzinfo=timezone.utc)

    CATALOG_TYPES = {
        "klines": "ohlcv",
        "open_interest": "open_interest",
        "funding": "funding_rate",
        "trades": "trades",
        "orderbook": "orderbook",
    }

    def __init__(
        self,
        catalog_root: Path | str | None = None,
        historical_root: Path | str | None = None,
        metrics_root: Path | str | None = None,
        normalized_root: Path | str | None = None,
    ):
        self.catalog_root = Path(catalog_root) if catalog_root is not None else self.CATALOG_ROOT
        self.historical_root = (
            Path(historical_root) if historical_root is not None else self.HISTORICAL_ROOT
        )
        self.metrics_root = Path(metrics_root) if metrics_root is not None else self.METRICS_ROOT
        self.normalized_root = Path(normalized_root) if normalized_root is not None else self.NORMALIZED_ROOT

    def check_readiness(
        self, 
        symbol: str, 
        snapshot_ts: str, 
        channel: str
    ) -> ReadinessReport:
        """Check readiness for Bybit artifact export."""
        dt = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
        
        # Define requirements per channel
        requirements = []
        
        # Base requirements for bybit_standard
        # 1. Klines (OHLCV)
        requirements.append(ReadinessRequirement(
            "klines",
            [
                str(self._catalog_file("klines", symbol, date_str)),
            ],
            True
        ))
        
        # 2. Open Interest
        requirements.append(ReadinessRequirement(
            "open_interest",
            [
                str(self._catalog_file("open_interest", symbol, date_str)),
                str(self.metrics_root / "open_interest")
            ],
            True
        ))
        
        # 3. Funding
        requirements.append(ReadinessRequirement(
            "funding",
            [
                str(self._catalog_file("funding", symbol, date_str)),
                str(self.metrics_root / "funding_rates")
            ],
            True
        ))
        
        # 4. Trades
        requirements.append(ReadinessRequirement(
            "trades",
            [
                str(self._catalog_file("trades", symbol, date_str)),
                str(self._historical_file("trades", symbol, date_str))
            ],
            True
        ))
        
        if channel == "depth_weighted":
            # 5. Orderbook
            requirements.append(ReadinessRequirement(
                "orderbook",
                [
                    str(self._catalog_file("orderbook", symbol, date_str)),
                    str(self._historical_file("orderbook", symbol, date_str))
                ],
                True
            ))

        details = {}
        status = "available"
        
        for req in requirements:
            source_status, found_path, reason = self._check_requirement(
                req.input_class, symbol, date_str
            )
            found = source_status != "missing"
            
            details[req.input_class] = {
                "present": found,
                "path": found_path if found else req.paths[0],
                "required": req.required,
                "source_status": source_status,
            }
            if reason:
                details[req.input_class]["reason"] = reason
            
            if source_status == "historical_raw_unnormalized" and req.required and status == "available":
                status = "blocked_source_unverified"
            elif not found and req.required:
                status = "blocked_source_missing"

        # Special gap check for orderbook
        if channel == "depth_weighted":
            if self.ORDERBOOK_GAP_START <= dt < self.ORDERBOOK_GAP_END_EXCLUSIVE:
                status = "blocked_source_missing"
                if "orderbook" not in details:
                     details["orderbook"] = {"present": False, "required": True}
                details["orderbook"]["status"] = "in_gap"
                details["orderbook"]["reason"] = "Orderbook gap 2025-08-21 to 2026-04-05 inclusive"

        return ReadinessReport(
            exchange="bybit",
            snapshot_ts=snapshot_ts,
            channel=channel,
            status=status,
            details=details
        )

    def _catalog_file(self, input_class: str, symbol: str, date_str: str) -> Path:
        catalog_type = self.CATALOG_TYPES[input_class]
        return self.catalog_root / catalog_type / f"{symbol}-PERP.BYBIT" / f"{date_str}.parquet"

    def _normalized_file(self, input_class: str, symbol: str, date_str: str) -> Path:
        return self.normalized_root / input_class / f"{symbol}-PERP.BYBIT" / f"{date_str}.parquet"

    def _historical_file(self, input_class: str, symbol: str, date_str: str) -> Path | None:
        if input_class == "klines":
            return self.historical_root / "klines" / "linear" / symbol / "1m" / f"{symbol}_1m_{date_str}.json"
        if input_class == "trades":
            return (
                self.historical_root
                / "trade"
                / "contract"
                / symbol
                / "contract"
                / "trade"
                / symbol
                / f"{symbol}{date_str}.csv.gz"
            )
        if input_class == "orderbook":
            return (
                self.historical_root
                / "orderbook"
                / "contract"
                / symbol
                / "contract"
                / "orderbook"
                / symbol
                / f"{date_str}_{symbol}_ob500.data.zip"
            )
        return None

    def _metrics_dir(self, input_class: str) -> Path | None:
        if input_class == "funding":
            return self.metrics_root / "funding_rates"
        if input_class == "open_interest":
            return self.metrics_root / "open_interest"
        return None

    def _check_requirement(
        self, input_class: str, symbol: str, date_str: str
    ) -> tuple[str, str | None, str | None]:
        catalog_file = self._catalog_file(input_class, symbol, date_str)
        if catalog_file.exists():
            return "catalog_file", str(catalog_file), None

        normalized_file = self._normalized_file(input_class, symbol, date_str)
        if normalized_file.exists():
            return "normalized_historical", str(normalized_file), None

        historical_file = self._historical_file(input_class, symbol, date_str)
        if historical_file and historical_file.exists():
            return (
                "historical_raw_unnormalized",
                str(historical_file),
                "Raw historical source exists but has not been normalized yet; "
                "run the historical bridge to produce a normalized parquet",
            )

        metrics_dir = self._metrics_dir(input_class)
        if metrics_dir and metrics_dir.exists() and any(metrics_dir.glob(f"{symbol}_*.json")):
            return (
                "historical_raw_unnormalized",
                str(metrics_dir),
                "Raw historical metric source exists but has not been normalized yet; "
                "run the historical bridge to produce a normalized parquet",
            )

        return "missing", None, None
