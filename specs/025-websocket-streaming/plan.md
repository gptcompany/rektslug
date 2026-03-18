# Plan: Spec 025 — WebSocket Real-Time Streaming

## Approach

Add FastAPI native WebSocket endpoints that push pre-computed payloads to
subscribed clients. The ConnectionManager partitions subscribers by
`(stream_type, symbol, variant)`. Broadcast is triggered by post-ingestion hooks.

Frontend falls back to REST polling if WebSocket is unavailable.

## Phases

### Phase 1: ConnectionManager

Implement the core connection management with subscriber tracking.

**Files to create**:
- `src/liquidationheatmap/api/websocket.py` — ConnectionManager class

**Design**:
```python
SubscriptionKey = tuple[str, str, str]  # (stream_type, symbol, variant)
# e.g. ("heatmap", "BTCUSDT", "15m") or ("liqmap", "ETHUSDT", "1w")

class ConnectionManager:
    def __init__(self, max_per_key: int = 100):
        self._subscribers: dict[SubscriptionKey, set[WebSocket]] = {}

    async def connect(self, key: SubscriptionKey, ws: WebSocket) -> bool
    async def disconnect(self, key: SubscriptionKey, ws: WebSocket)
    async def broadcast(self, key: SubscriptionKey, payload: dict)
    async def heartbeat_loop(self)  # 30s ping to all connections
```

### Phase 2: WebSocket Endpoints

Add the two WS routes to FastAPI.

**Files to modify**:
- `src/liquidationheatmap/api/main.py` — mount WS routes

**Endpoints**:
- `ws://host/ws/heatmap/{symbol}/{interval}` — streams heatmap timeseries snapshots
- `ws://host/ws/liqmap/{symbol}/{timeframe}` — streams liq-map updates

### Phase 3: Broadcast Trigger

Wire post-ingestion hook to broadcast fresh data.

**Files to modify**:
- `src/liquidationheatmap/api/routers/admin.py` — after gap-fill success, call `manager.broadcast()`
- `scripts/run-ingestion.sh` — optional: curl trigger for broadcast after gap-fill

**Payload**: Same JSON as REST endpoints (no new schema).

### Phase 4: Frontend WebSocket Client

Add WS client to existing frontend pages with polling fallback.

**Files to modify**:
- `frontend/liq_map_1w.html` — add WS client for liqmap stream
- `frontend/coinglass_heatmap.html` — add WS client for heatmap stream

**Pattern**:
```javascript
function connectWebSocket(url, onMessage) {
    const ws = new WebSocket(url);
    ws.onmessage = (event) => onMessage(JSON.parse(event.data));
    ws.onclose = () => setTimeout(() => connectWebSocket(url, onMessage), 5000);
    ws.onerror = () => ws.close();  // triggers onclose → reconnect
    return ws;
}
```

### Phase 5: Tests & Performance Gates

**Files to create**:
- `tests/unit/api/test_websocket.py` — ConnectionManager unit tests
- `tests/integration/test_websocket_e2e.py` — full WS connect/receive/disconnect

**Gates**:
- Broadcast latency < 5s
- Memory per connection < 1MB
- 100 concurrent connections: REST response time degradation < 10%

## Dependencies

- spec-024 heatmap cache (provides pre-computed payloads for heatmap stream)
- spec-022 public builder (provides liq-map payloads)
- FastAPI WebSocket support (built-in, no extra deps)

## Risk

- WebSocket connections behind Cloudflare Access may require tunnel config.
  Mitigation: test locally first, add CF WebSocket support in deployment phase.
- Memory pressure with many connections.
  Mitigation: cap at 100/key, monitor via Prometheus gauge.
