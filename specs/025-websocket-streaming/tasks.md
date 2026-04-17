# Tasks: WebSocket Real-Time Streaming

**Input**: `specs/025-websocket-streaming/spec.md`
**Dependencies**: spec-024 (heatmap cache), spec-022 (public builder)
**Feature Type**: Backend + Frontend

## Phase 1: ConnectionManager

- [x] T001 Create `src/liquidationheatmap/api/websocket.py` with ConnectionManager class
- [x] T002 Implement `connect(key, ws)` with per-key cap (100 max)
- [x] T003 Implement `disconnect(key, ws)` with cleanup
- [x] T004 Implement `broadcast(key, payload)` with error-tolerant send
- [x] T005 Implement `heartbeat_loop()` — 30s ping, prune stale connections
- [x] T006 Add unit tests for ConnectionManager (connect, disconnect, broadcast, cap)

**Checkpoint**: ConnectionManager handles subscriber lifecycle correctly.

## Phase 2: WebSocket Endpoints

- [x] T007 Add `ws://host/ws/heatmap/{symbol}/{interval}` endpoint to main.py
- [x] T008 Add `ws://host/ws/liqmap/{symbol}/{timeframe}` endpoint to main.py
- [x] T009 Validate path params (symbol in SUPPORTED_SYMBOLS, interval/timeframe valid)
- [x] T010 Add integration test: connect, receive heartbeat, disconnect cleanly

**Checkpoint**: WebSocket endpoints accept and hold connections.

## Phase 3: Broadcast Trigger

- [x] T011 Wire post-gap-fill success in admin router to call `manager.broadcast()`
- [x] T012 Heatmap broadcast: read latest cached snapshot from spec-024 cache table
- [x] T013 Liqmap broadcast: call public builder for latest liq-map payload
- [x] T014 Add `/admin/ws-broadcast` manual trigger for testing
- [x] T015 Add integration test: gap-fill triggers broadcast, connected client receives data

**Checkpoint**: Data flows from ingestion to connected clients.

## Phase 4: Frontend WebSocket Client

- [x] T016 Add WS client to `frontend/liq_map_1w.html` with auto-reconnect
- [x] T017 Add WS client to `frontend/coinglass_heatmap.html` with auto-reconnect
- [x] T018 Implement polling fallback: if WS fails 3x, revert to setInterval fetch
- [x] T019 Visual test: verify chart updates without manual page refresh

**Checkpoint**: Frontend receives live updates.

## Phase 5: Observability & Performance

- [x] T020 Add Prometheus gauge `lh_ws_active_connections` (labels: stream_type, symbol)
- [x] T021 Add Prometheus counter `lh_ws_broadcasts_total`
- [x] T022 [P] Performance test: broadcast latency < 5 seconds
- [x] T023 [P] Performance test: memory per connection < 1MB
- [x] T024 [P] Performance test: 100 connections, REST degradation < 10%
- [x] T025 Full regression test — confirm no impact on existing endpoints

**Checkpoint**: All performance gates pass.

## Dependencies

```
Phase 1 (ConnectionManager)
  └─→ Phase 2 (endpoints)
        └─→ Phase 3 (broadcast trigger) ── depends on spec-024 cache
              └─→ Phase 4 (frontend client)
                    └─→ Phase 5 (observability + perf)
```

T022-T024 parallel.

## MVP Strategy

1. Phase 1-2: ConnectionManager + endpoints (testable without live data)
2. Phase 3: broadcast wiring (needs running API + gap-fill)
3. Phase 4-5: frontend + perf (needs full stack)
