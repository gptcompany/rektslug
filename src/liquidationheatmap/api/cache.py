import time
import logging
from typing import Optional, Any
from src.liquidationheatmap.settings import get_settings

logger = logging.getLogger(__name__)

class HeatmapCache:
    """In-memory cache with TTL for heatmap timeseries responses."""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 100):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: dict[str, tuple[float, Any]] = {}  # key -> (expiry_time, value)
        self._hits = 0
        self._misses = 0

    def _make_key(
        self,
        symbol: str,
        start_time: Optional[str],
        end_time: Optional[str],
        interval: str,
        price_bin_size: float,
        leverage_weights: Optional[str],
    ) -> str:
        return f"{symbol}:{start_time}:{end_time}:{interval}:{price_bin_size}:{leverage_weights}"

    def get(
        self,
        symbol: str,
        start_time: Optional[str],
        end_time: Optional[str],
        interval: str,
        price_bin_size: float,
        leverage_weights: Optional[str],
    ) -> Optional[Any]:
        key = self._make_key(
            symbol, start_time, end_time, interval, price_bin_size, leverage_weights
        )
        if key in self._cache:
            expiry, value = self._cache[key]
            if time.time() < expiry:
                self._hits += 1
                return value
            else:
                del self._cache[key]

        self._misses += 1
        return None

    def set(
        self,
        symbol: str,
        start_time: Optional[str],
        end_time: Optional[str],
        interval: str,
        price_bin_size: float,
        leverage_weights: Optional[str],
        value: Any,
    ) -> None:
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]

        key = self._make_key(
            symbol, start_time, end_time, interval, price_bin_size, leverage_weights
        )
        expiry = time.time() + self.ttl_seconds
        self._cache[key] = (expiry, value)

    def get_stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total,
            "hit_rate_percent": round(hit_rate, 2),
            "cached_entries": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
        }

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

# Singleton instance
settings = get_settings()
heatmap_cache = HeatmapCache(
    ttl_seconds=settings.cache_ttl,
    max_size=settings.cache_max_size,
)
