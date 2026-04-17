import hashlib
import json
import logging
import zipfile
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
            return self.metrics_root / "funding_rates" / symbol / f"{date_str}.json"
        if input_class == "open_interest":
            return self.metrics_root / "open_interest" / symbol / f"{date_str}.json"
        return None

    def read_raw(self, input_class: str, path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()

        try:
            if input_class == "klines":
                return self._read_klines(path)
            elif input_class == "trades":
                return self._read_trades(path)
            elif input_class == "orderbook":
                return self._read_orderbook(path)
            elif input_class == "funding":
                return self._read_funding(path)
            elif input_class == "open_interest":
                return self._read_open_interest(path)
        except Exception as e:
            logger.warning(f"Failed to read {input_class} from {path}: {e}")
            return pd.DataFrame()

        return pd.DataFrame()

    def _read_klines(self, path: Path) -> pd.DataFrame:
        with open(path, "r") as f:
            data = json.load(f)
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["close"] = df["close"].astype(float)
        return df

    def _read_trades(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path, compression="gzip" if path.suffix == ".gz" else None)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def _read_orderbook(self, path: Path) -> pd.DataFrame:
        """Read orderbook from Bybit .data.zip archive.

        The archive contains one or more CSV files with columns:
        timestamp, side, price, size (one row per level per snapshot).
        We pivot into a wide format compatible with the producer.
        """
        frames = []
        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".csv"):
                    continue
                with zf.open(name) as inner:
                    df = pd.read_csv(inner)
                    frames.append(df)
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def _read_funding(self, path: Path) -> pd.DataFrame:
        """Read funding rate JSON (metrics downloader format).

        Expected: JSON array of objects with at least
        ``funding_rate``, ``funding_rate_timestamp``.
        """
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
        if not isinstance(data, list) or not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        if "funding_rate_timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["funding_rate_timestamp"], unit="ms", utc=True)
        elif "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        if "funding_rate" in df.columns:
            df["funding_rate"] = df["funding_rate"].astype(float)
        return df

    def _read_open_interest(self, path: Path) -> pd.DataFrame:
        """Read open interest JSON (metrics downloader format).

        Expected: JSON array of objects with at least
        ``open_interest``, ``timestamp``.
        """
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
        if not isinstance(data, list) or not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        if "open_interest" in df.columns:
            df["open_interest_value"] = df["open_interest"].astype(float)
        return df

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
