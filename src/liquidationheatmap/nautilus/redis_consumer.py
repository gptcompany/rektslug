import asyncio
import json
import logging
import time
from typing import Callable, Optional

import redis.asyncio as redis
from src.liquidationheatmap.nautilus.data import LiquidationSignalData, iso_to_nanos
from src.liquidationheatmap.signals.config import get_redis_config

logger = logging.getLogger(__name__)

class NautilusSignalConsumer:
    """Consumes LiquidationSignals from Redis and emits Nautilus events."""

    def __init__(self, redis_config=None):
        self.config = redis_config or get_redis_config()
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None

    async def connect(self):
        self.redis_client = redis.from_url(self.config.url, decode_responses=True)
        self.pubsub = self.redis_client.pubsub()

    def _process_message(self, message_data: str) -> Optional[LiquidationSignalData]:
        """Convert a Redis JSON message to a LiquidationSignalData event."""
        try:
            data = json.loads(message_data)
            return LiquidationSignalData(
                ts_event=iso_to_nanos(data["timestamp"]),
                ts_init=int(time.time() * 1_000_000_000),
                symbol=data["symbol"],
                price=float(data["price"]),
                side=data["side"],
                confidence=float(data["confidence"]),
                source=data["source"],
                signal_id=data.get("signal_id")
            )
        except Exception as e:
            logger.error(f"Failed to parse signal from Redis: {e}")
            return None

    async def listen_forever(self, symbols: list[str], callback: Callable[[LiquidationSignalData], None]):
        """Main loop for consuming messages from all subscribed channels."""
        if not self.pubsub:
            await self.connect()
            
        channels = [f"liquidation:signals:{s}" for s in symbols]
        await self.pubsub.subscribe(*channels)
        logger.info(f"Nautilus consumer subscribed to {channels}")
        
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    signal = self._process_message(message["data"])
                    if signal:
                        callback(signal)
        finally:
            await self.pubsub.unsubscribe(*channels)
            await self.redis_client.close()
