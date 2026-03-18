# Spec 025: WebSocket Real-Time Streaming

## Overview

Add WebSocket endpoints to push liquidation heatmap updates to connected clients
in real-time, replacing the current polling-based frontend refresh cycle.

This was originally scoped in spec-011 but never implemented. This spec is a
pragmatic subset focused on the minimum viable streaming path: server-push of
pre-computed heatmap snapshots over WebSocket, with no client-side computation.

## Scope

### In Scope

- WebSocket endpoint `ws://host/ws/heatmap/{symbol}/{interval}` for streaming heatmap snapshots (interval: `15m` or `1h`)
- WebSocket endpoint `ws://host/ws/liqmap/{symbol}/{timeframe}` for streaming liq-map updates (timeframe: `1d` or `1w`)
- Server-side publish loop tied to ingestion/gap-fill events
- Client heartbeat and reconnection protocol
- Frontend WebSocket client in `coinglass_heatmap.html` and `liq_map_1w.html`
- Connection lifecycle: auth-free, rate-limited to 1 message/interval

### Out of Scope

- Redis pub/sub fan-out (single-server only for MVP)
- Client-side computation or differential updates
- Authentication/authorization on WebSocket (defer to reverse proxy)
- Multi-exchange aggregated streams
- Historical replay over WebSocket

## Dependencies

- spec-024 heatmap timeseries cache (provides pre-computed snapshots to stream)
- spec-022 public liqmap builder (provides liq-map payloads)
- FastAPI WebSocket support (built-in)

## Architectural Decision

- Use FastAPI native WebSocket, not Socket.IO or external broker.
- Server maintains a `ConnectionManager` with subscriber sets keyed by `(stream_type, symbol, variant)` where variant is interval for heatmap or timeframe for liqmap.
- Publish trigger: post-gap-fill hook calls `ConnectionManager.broadcast(stream_type, symbol, variant)`.
- Payload: same JSON shape as REST endpoints (no new schema).
- Graceful degradation: if no WebSocket, frontend falls back to polling (existing behavior).

## Functional Requirements

- **FR-001**: Connected clients MUST receive new data within 5 seconds of ingestion completion.
- **FR-002**: Server MUST send periodic heartbeat (every 30s) to detect stale connections.
- **FR-003**: Client disconnect MUST NOT affect other subscribers or server stability.
- **FR-004**: Server MUST cap concurrent connections at 100 per symbol.
- **FR-005**: Frontend MUST gracefully fall back to REST polling if WebSocket fails.
- **FR-006**: WebSocket payload MUST be identical in structure to the REST response.

## Performance Gates

- **PG-001**: Broadcast latency (ingestion complete to client receive) < 5 seconds.
- **PG-002**: Memory overhead per connection < 1MB.
- **PG-003**: 100 concurrent connections MUST NOT degrade REST API response time by > 10%.

## Success Criteria

- **SC-001**: Frontend receives live updates without manual refresh.
- **SC-002**: Connection survives 1 hour without dropping under normal conditions.
- **SC-003**: Fallback to polling works transparently when WebSocket is unavailable.
- **SC-004**: No regression on existing REST endpoints or ingestion pipeline.
