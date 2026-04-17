"""Signal Publisher for Adaptive Signal Loop.

Publishes top liquidation zones to Redis pub/sub for consumption by
Nautilus (trading) and UTXOracle (dashboard).
"""

from __future__ import annotations

import argparse
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.liquidationheatmap.signals.config import get_signal_channel, get_signal_config
from src.liquidationheatmap.signals.models import LiquidationSignal
from src.liquidationheatmap.signals.redis_client import RedisClient, get_redis_client

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SignalPublisher:
    """Publishes liquidation signals to Redis.

    Attributes:
        redis_client: Redis client for pub/sub
        config: Signal configuration

    Usage:
        publisher = SignalPublisher()
        publisher.publish_signal("BTCUSDT", 95000.0, "long", 0.85)

        # Or from heatmap data
        signals = publisher.extract_top_signals("BTCUSDT", heatmap_data, top_n=5)
        publisher.publish_batch(signals)
    """

    def __init__(self, redis_client: RedisClient | None = None):
        """Initialize SignalPublisher.

        Args:
            redis_client: Redis client (uses global client if None)
        """
        self._redis_client = redis_client
        self._config = get_signal_config()

    @property
    def redis_client(self) -> RedisClient:
        """Get Redis client (lazy initialization)."""
        if self._redis_client is None:
            self._redis_client = get_redis_client()
        return self._redis_client

    def publish_signal(
        self,
        symbol: str,
        price: float | Decimal,
        side: str,
        confidence: float,
        signal_id: str | None = None,
    ) -> bool:
        """Publish a single liquidation signal to Redis.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            price: Liquidation price level
            side: Position side ('long' or 'short')
            confidence: Signal confidence (0.0-1.0)
            signal_id: Optional unique identifier

        Returns:
            True if published successfully, False otherwise
        """
        if not self._config.enabled:
            logger.debug("Signals disabled, skipping publish")
            return False

        signal = LiquidationSignal(
            symbol=symbol,
            price=Decimal(str(price)),
            side=side,
            confidence=confidence,
            signal_id=signal_id or str(uuid.uuid4())[:8],
        )

        channel = get_signal_channel(symbol, "signals")
        result = self.redis_client.publish(channel, signal.to_redis_message())

        if result is not None:
            logger.info(
                f"Published signal to {channel}: "
                f"price={signal.price}, side={signal.side}, confidence={signal.confidence}"
            )
            # Update persisted and in-memory status tracking on successful publish.
            self._update_last_publish(signal.signal_id)
            return True
        else:
            logger.warning(f"Failed to publish signal to {channel}")
            return False

    def _update_last_publish(self, signal_id: str | None) -> None:
        """Update persisted and in-memory publish metrics for API status tracking."""
        published_at = datetime.now(timezone.utc)
        try:
            from src.liquidationheatmap.api.routers.signals import set_last_publish
            from src.liquidationheatmap.signals.status_store import record_signal_publish

            set_last_publish(published_at)
            record_signal_publish(self.redis_client, published_at, signal_id)
        except ImportError:
            # API router may not be available (e.g., in tests or standalone mode)
            pass

    def publish_batch(self, signals: list[LiquidationSignal]) -> int:
        """Publish multiple signals.

        Args:
            signals: List of LiquidationSignal objects

        Returns:
            Number of signals successfully published
        """
        if not self._config.enabled:
            logger.debug("Signals disabled, skipping batch publish")
            return 0

        published = 0
        for signal in signals:
            if signal.signal_id is None:
                signal.signal_id = str(uuid.uuid4())[:8]

            channel = get_signal_channel(signal.symbol, "signals")
            result = self.redis_client.publish(channel, signal.to_redis_message())

            if result is not None:
                published += 1
                self._update_last_publish(signal.signal_id)
                logger.debug(f"Published signal {signal.signal_id} to {channel}")
            else:
                logger.warning(f"Failed to publish signal {signal.signal_id}")

        logger.info(f"Published {published}/{len(signals)} signals")
        return published

    def extract_top_signals(
        self,
        symbol: str,
        heatmap_data: dict[str, Any],
        top_n: int | None = None,
    ) -> list[LiquidationSignal]:
        """Extract top N signals from heatmap data.

        Args:
            symbol: Trading pair
            heatmap_data: Heatmap calculation result with 'zones' key
            top_n: Number of top signals (uses config default if None)

        Returns:
            List of LiquidationSignal objects, sorted by confidence (highest first)
        """
        if top_n is None:
            top_n = self._config.top_n

        zones = heatmap_data.get("zones", [])
        if not zones:
            logger.debug(f"No zones in heatmap data for {symbol}")
            return []

        # Sort by intensity (confidence) descending
        sorted_zones = sorted(zones, key=lambda z: z.get("intensity", 0), reverse=True)

        # Take top N
        top_zones = sorted_zones[:top_n]

        # Convert to signals (skip invalid zones)
        signals = []
        for zone in top_zones:
            price = zone.get("price", 0)
            if price <= 0:
                logger.warning(f"Skipping zone with invalid price: {price}")
                continue
            try:
                signal = LiquidationSignal(
                    symbol=symbol,
                    price=Decimal(str(price)),
                    side=zone.get("side", "long"),
                    confidence=zone.get("intensity", 0),
                    signal_id=str(uuid.uuid4())[:8],
                )
                signals.append(signal)
            except ValueError as e:
                logger.warning(f"Skipping invalid zone: {e}")
                continue

        logger.debug(f"Extracted {len(signals)} top signals from heatmap for {symbol}")
        return signals

    def publish_from_heatmap(
        self,
        symbol: str,
        heatmap_data: dict[str, Any],
        top_n: int | None = None,
    ) -> int:
        """Extract and publish top signals from heatmap data.

        Convenience method that combines extract_top_signals and publish_batch.

        Args:
            symbol: Trading pair
            heatmap_data: Heatmap calculation result
            top_n: Number of top signals

        Returns:
            Number of signals published
        """
        signals = self.extract_top_signals(symbol, heatmap_data, top_n)
        if signals:
            return self.publish_batch(signals)
        return 0

    def publish_from_snapshot(
        self,
        snapshot: Any,  # HeatmapSnapshot but using Any to avoid circular imports
        top_n: int | None = None,
    ) -> int:
        """Publish top signals from a HeatmapSnapshot.

        Converts HeatmapSnapshot cells to the signal format expected by extract_top_signals.

        Args:
            snapshot: HeatmapSnapshot object from time_evolving_heatmap
            top_n: Number of top signals (uses config default if None)

        Returns:
            Number of signals published
        """
        # Convert HeatmapSnapshot cells to zones format
        zones = []
        for cell in snapshot.cells.values():
            # Add long zone if significant
            if cell.long_density > 0:
                zones.append(
                    {
                        "price": float(cell.price_bucket),
                        "intensity": float(cell.long_density),
                        "side": "long",
                    }
                )
            # Add short zone if significant
            if cell.short_density > 0:
                zones.append(
                    {
                        "price": float(cell.price_bucket),
                        "intensity": float(cell.short_density),
                        "side": "short",
                    }
                )

        heatmap_data = {"zones": zones}
        return self.publish_from_heatmap(snapshot.symbol, heatmap_data, top_n)

    def close(self) -> None:
        """Close Redis connection."""
        if self._redis_client is not None:
            self._redis_client.disconnect()


# Global publisher instance for integration with heatmap calculation
_global_publisher: SignalPublisher | None = None


def get_publisher() -> SignalPublisher:
    """Get global SignalPublisher (singleton)."""
    global _global_publisher
    if _global_publisher is None:
        _global_publisher = SignalPublisher()
    return _global_publisher


def publish_signals_from_snapshot(snapshot: Any, top_n: int | None = None) -> int:
    """Convenience function to publish signals from heatmap snapshot.

    Call this from time_evolving_heatmap.calculate_time_evolving_heatmap()
    to integrate signal publishing into the heatmap pipeline.

    Args:
        snapshot: HeatmapSnapshot object
        top_n: Number of top signals

    Returns:
        Number of signals published
    """
    publisher = get_publisher()
    return publisher.publish_from_snapshot(snapshot, top_n)


def main():
    """CLI entry point for manual signal publishing."""
    parser = argparse.ArgumentParser(description="Publish liquidation signals to Redis")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair symbol")
    parser.add_argument("--price", type=float, required=True, help="Liquidation price")
    parser.add_argument("--side", choices=["long", "short"], required=True, help="Position side")
    parser.add_argument("--confidence", type=float, default=0.5, help="Signal confidence (0.0-1.0)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    publisher = SignalPublisher()
    try:
        result = publisher.publish_signal(
            symbol=args.symbol,
            price=args.price,
            side=args.side,
            confidence=args.confidence,
        )
        if result:
            print(f"Signal published successfully to liquidation:signals:{args.symbol}")
        else:
            print("Failed to publish signal")
    finally:
        publisher.close()


if __name__ == "__main__":
    main()
