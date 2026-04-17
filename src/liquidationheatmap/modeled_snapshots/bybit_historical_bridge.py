import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

class BybitHistoricalBridge:
    HISTORICAL_ROOT = Path("/media/sam/3TB-WDC/bybit_data_downloader/data/historical")
    NORMALIZED_ROOT = Path("/media/sam/1TB/rektslug/data/historical_normalized/bybit")
    METRICS_ROOT = Path("/media/sam/3TB-WDC/bybit_data_downloader/data/market_metrics")

    def __init__(
        self, 
        historical_root: Path | str | None = None, 
        normalized_root: Path | str | None = None,
        metrics_root: Path | str | None = None
    ):
        self.historical_root = Path(historical_root) if historical_root is not None else self.HISTORICAL_ROOT
        self.normalized_root = Path(normalized_root) if normalized_root is not None else self.NORMALIZED_ROOT
        self.metrics_root = Path(metrics_root) if metrics_root is not None else self.METRICS_ROOT

    def resolve_raw_path(self, symbol: str, date_str: str, input_class: str) -> Path | None:
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
        if input_class == "funding":
            return self.metrics_root / "funding_rates"
        if input_class == "open_interest":
            return self.metrics_root / "open_interest"
        return None

    def read_raw(self, input_class: str, path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()
            
        if input_class == "klines":
            with open(path, "r") as f:
                data = json.load(f)
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df["close"] = df["close"].astype(float)
            return df
        elif input_class == "trades":
            # Just read the csv and convert timestamp if exists
            try:
                df = pd.read_csv(path, compression="gzip" if path.suffix == ".gz" else None)
                if "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                return df
            except Exception:
                return pd.DataFrame()
        elif input_class in ["funding", "open_interest"]:
            # Typically json arrays from the metrics downloader
            # path is the directory, we need to read all json files and concat or just read one for the exact date
            return pd.DataFrame()
            
        return pd.DataFrame()

    def write_normalized(self, df: pd.DataFrame, input_class: str, symbol: str, date_str: str, source_path: str) -> Tuple[Path, Dict[str, Any]]:
        dest = self.normalized_root / input_class / f"{symbol}-PERP.BYBIT" / f"{date_str}.parquet"
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        df.to_parquet(dest)
        
        # Calculate simple digest
        with open(dest, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
            
        meta = {
            "source_path": source_path,
            "digest": digest
        }
        
        meta_path = dest.with_suffix(".json")
        with open(meta_path, "w") as f:
            json.dump(meta, f)
            
        return dest, meta
