# Exchange Integration Guide

This guide explains how to add new exchange adapters to the LiquidationHeatmap system.

## Architecture Overview

The exchange integration follows an **Adapter Pattern**:

```
┌─────────────────────┐
│  ExchangeAggregator │  Manages multiple adapters, multiplexes streams
└─────────┬───────────┘
          │
    ┌─────┴─────┬─────────────┐
    ▼           ▼             ▼
┌────────┐ ┌────────────┐ ┌────────┐
│Binance │ │Hyperliquid │ │ Bybit  │
│Adapter │ │  Adapter   │ │Adapter │
└────────┘ └────────────┘ └────────┘
   REST       Legacy/Off     Stub
  Polling
```

## Base Classes

### `NormalizedLiquidation`

All adapters must yield this standardized dataclass:

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class NormalizedLiquidation:
    exchange: str           # "binance", "hyperliquid", "bybit"
    timestamp: datetime     # UTC timestamp
    symbol: str             # Normalized: "BTCUSDT"
    side: str               # "long" or "short"
    price: float            # Liquidation price
    quantity: float         # Size in base currency
    notional: float         # USD value (price * quantity)
    order_id: str | None    # Exchange-specific order ID
```

### `ExchangeAdapter` (Abstract Base Class)

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class ExchangeAdapter(ABC):
    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Return exchange identifier."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to exchange."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection gracefully."""

    @abstractmethod
    async def stream_liquidations(self) -> AsyncIterator[NormalizedLiquidation]:
        """Yield normalized liquidation events."""

    @abstractmethod
    async def health_check(self) -> ExchangeHealth:
        """Return current connection health."""
```

## Implementing a New Adapter

### Step 1: Create Adapter File

Create `src/exchanges/your_exchange.py`:

```python
from typing import AsyncIterator
from .base import ExchangeAdapter, NormalizedLiquidation, ExchangeHealth

class YourExchangeAdapter(ExchangeAdapter):

    @property
    def exchange_name(self) -> str:
        return "your_exchange"

    async def connect(self) -> None:
        # Initialize connection (REST session or WebSocket)
        pass

    async def disconnect(self) -> None:
        # Clean up resources
        pass

    async def stream_liquidations(self) -> AsyncIterator[NormalizedLiquidation]:
        # Yield normalized events
        while True:
            raw_event = await self._fetch_next_event()
            yield self._normalize(raw_event)

    async def health_check(self) -> ExchangeHealth:
        return ExchangeHealth(
            exchange=self.exchange_name,
            is_connected=self._is_connected,
            last_heartbeat=self._last_heartbeat,
            error_count=self._error_count,
        )
```

### Step 2: Symbol Normalization

Each exchange uses different symbol formats. Implement normalization:

```python
def normalize_symbol(self, exchange_symbol: str) -> str:
    """Convert exchange format to standard BTCUSDT format."""
    # Binance: "BTCUSDT" -> "BTCUSDT" (already standard)
    # Hyperliquid sidecar/cache paths still normalize "BTC" -> "BTCUSDT"
    # Bybit: "BTCUSD" -> "BTCUSDT"
    return exchange_symbol.replace("USD", "USDT")
```

### Step 3: Side Mapping

Liquidation sides vary by exchange:

| Exchange | Long Liquidation | Short Liquidation |
|----------|-----------------|-------------------|
| Binance | `"SELL"` | `"BUY"` |
| Hyperliquid | `"B"` (Bid) | `"A"` (Ask) |
| Bybit | `"Sell"` | `"Buy"` |

```python
def _normalize_side(self, raw_side: str) -> str:
    """Map exchange-specific side to 'long' or 'short'."""
    side_map = {
        "SELL": "long",   # Long positions get force-sold
        "BUY": "short",   # Short positions get force-bought
    }
    return side_map.get(raw_side.upper(), "unknown")
```

### Step 4: Register Adapter

Add to `src/exchanges/__init__.py`:

```python
from .your_exchange import YourExchangeAdapter

__all__ = [
    ...,
    "YourExchangeAdapter",
]
```

Add to `src/exchanges/aggregator.py`:

```python
SUPPORTED_EXCHANGES = {
    "binance": BinanceAdapter,
    "hyperliquid": HyperliquidAdapter,
    "your_exchange": YourExchangeAdapter,
}
```

### Step 5: Write Tests

Create `tests/test_exchanges/test_your_exchange.py`:

```python
import pytest
from src.exchanges.your_exchange import YourExchangeAdapter

class TestYourExchangeAdapter:
    def test_exchange_name(self):
        adapter = YourExchangeAdapter()
        assert adapter.exchange_name == "your_exchange"

    def test_normalize_symbol(self):
        adapter = YourExchangeAdapter()
        assert adapter.normalize_symbol("BTCUSD") == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_connect(self):
        adapter = YourExchangeAdapter()
        await adapter.connect()
        health = await adapter.health_check()
        assert health.is_connected
        await adapter.disconnect()
```

## Connection Strategies

### REST Polling (Binance)

For exchanges without real-time liquidation WebSocket:

```python
async def stream_liquidations(self):
    while self._is_connected:
        async with self._session.get(self._endpoint) as resp:
            data = await resp.json()
            for event in data:
                if self._is_new(event):
                    yield self._normalize(event)
        await asyncio.sleep(5)  # 5s poll interval
```

### Hyperliquid Runtime Boundary

Hyperliquid does not use the public WebSocket as the canonical source of
realized liquidation events in the active runtime.

- Realized liquidations: ingest from `node_fills_by_block` via
  `scripts/ingest_hl_fills.py`
- Public Hyperliquid liq-map: serve from `/liquidations/hl-public-map`
- Legacy public-WS liquidation adapters are retained only for backwards
  compatibility and fail fast as unsupported

## Deduplication

Implement order ID tracking to prevent duplicates:

```python
def __init__(self):
    self._seen_orders: set[str] = set()
    self._seen_orders_expiry: dict[str, datetime] = {}
    self._dedup_window = timedelta(minutes=10)

def _is_new(self, event: dict) -> bool:
    order_id = event.get("order_id")
    if order_id in self._seen_orders:
        return False
    self._seen_orders.add(order_id)
    self._seen_orders_expiry[order_id] = datetime.now(timezone.utc)
    self._cleanup_expired()
    return True
```

## Error Handling

Implement graceful degradation:

```python
async def stream_liquidations(self):
    retry_count = 0
    max_retries = 3
    backoff = [1, 2, 4]  # seconds

    while retry_count < max_retries:
        try:
            async for event in self._raw_stream():
                yield self._normalize(event)
                retry_count = 0  # Reset on success
        except Exception as e:
            self._error_count += 1
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(backoff[retry_count - 1])
            else:
                logger.error(f"Max retries reached: {e}")
                return
```

## API Endpoints

The aggregator exposes these API endpoints:

| Endpoint | Description |
|----------|-------------|
| `GET /exchanges` | List supported exchanges |
| `GET /exchanges/health` | Per-exchange health status |
| `GET /liquidations/heatmap-timeseries?exchanges=binance,hyperliquid` | Filter by exchange |

## Checklist for New Exchanges

- [ ] Create adapter class in `src/exchanges/`
- [ ] Implement all abstract methods
- [ ] Add symbol normalization
- [ ] Add side mapping (long/short)
- [ ] Implement deduplication
- [ ] Add reconnection logic
- [ ] Register in `SUPPORTED_EXCHANGES`
- [ ] Write unit tests
- [ ] Write integration test
- [ ] Update API validation
- [ ] Run load test
- [ ] Document exchange-specific quirks

## Current Exchange Support

| Exchange | Status | Connection | Notes |
|----------|--------|------------|-------|
| Binance | Active | REST 5s | Primary source |
| Hyperliquid | Sidecar/Node Fills | Not public WS | Realized liqs from node fills; public map from sidecar |
| Bybit | Stub | NotImplementedError | Future |
| OKX | Planned | TBD | Future |
