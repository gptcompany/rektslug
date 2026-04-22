# Continuous Runtime Contracts

This document defines the public interfaces and contracts required for the `rektslug` and `nautilus_dev` continuous paper/testnet runtime (Spec-040).

## 1. Feedback Consumer Redis Contract

The `rektslug-feedback-consumer` service listens for real-time P&L feedback from Nautilus over Redis pub/sub.

- **Dedicated feedback DB path:** `FEEDBACK_DB_PATH`
  - runtime default in compose: `/var/lib/rektslug-db/signal_feedback.duckdb`
  - kept separate from `/var/lib/rektslug-db/liquidations.duckdb` to avoid DuckDB writer lock contention with the shadow/runtime store

- **Channel Format:** `liquidation:feedback:{symbol}` (e.g., `liquidation:feedback:BTCUSDT`)
- **Message Format:** JSON
- **Schema:**
  ```json
  {
    "symbol": "BTCUSDT",
    "signal_id": "abc12345",
    "entry_price": "95000.00",
    "exit_price": "95500.00",
    "pnl": "500.00",
    "timestamp": "2025-12-28T11:00:00Z",
    "source": "nautilus"
  }
  ```
  *(Note: All prices and P&L must be valid Decimal strings for precision.)*

## 2. Continuous Report JSON Schema

The `GET /signals/continuous-report` API returns a machine-readable report containing exact runtime lifecycle counters.
It merges a runtime-generated execution snapshot with actual DuckDB writes (`feedback_persisted`).
If the runtime snapshot is missing or incomplete, the endpoint fails closed with `503` instead of returning placeholder zeros.

- **Endpoint:** `GET /signals/continuous-report`
- **Schema (ContinuousReport):**
  ```json
  {
    "session_started_at": "2026-03-01T11:00:00Z",
    "timestamp": "2026-03-01T12:00:00Z",
    "runtime_seconds": 3600.0,
    "signals_seen": 150,
    "signals_rejected": 50,
    "signals_accepted": 100,
    "orders_submitted": 100,
    "orders_rejected": 5,
    "orders_filled": 95,
    "positions_opened": 95,
    "positions_closed": 90,
    "feedback_published": 90,
    "feedback_persisted": 90,
    "persistence_consistent": true,
    "report_status": "ok",
    "blocking_issues": [],
    "residual_open_positions": 5,
    "residual_open_orders": 0
  }
  ```
  *(Note: `feedback_persisted` is derived directly from DuckDB rows whose `created_at` falls within the current session. `report_status` becomes `blocked` when blocking issues are detected, such as `feedback_published != feedback_persisted`.)*

- **Runtime snapshot source:**
  - Path from `HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH` or `CONTINUOUS_RUNTIME_REPORT_PATH`
  - Default fallback: `$(dirname HEATMAP_DB_PATH)/continuous_runtime_report.json`
- **Feedback persistence source:**
  - Path from `FEEDBACK_DB_PATH`
  - runtime default in compose: `/var/lib/rektslug-db/signal_feedback.duckdb`
- **Failure semantics:**
  - `503 Service Unavailable` if the runtime snapshot file is missing, unreadable, or missing required fields

## 3. Healthcheck Endpoints / Health Semantics

### API Healthcheck
The main API provides a health endpoint for the signal/feedback system:

- **Endpoint:** `GET /signals/status`
- **Returns:**
  ```json
  {
    "connected": true,
    "last_publish": "2025-12-28T10:30:00Z",
    "signals_published_24h": 96,
    "feedback_received_24h": 12
  }
  ```

## 4. Restart and Recovery Expectations (Fail-Closed Behavior)

### Nautilus Execution Service
The Nautilus continuous execution service (`nautilus-liquidation-paper-testnet`) is designed to fail closed.
- **Startup:** If the target environment (e.g., testnet) does not match the configuration, or if required secrets (`HYPERLIQUID_TESTNET_PK`) are missing, the service will refuse to start.
- **Redis Disconnect:** If the Redis connection drops, the service will halt entries (`fail_closed_on_redis_error=True`) and gracefully stop, writing a `HALTED` or `DEGRADED` runtime snapshot.
- **Restart/Recovery:** Upon restart, Nautilus queries the venue (e.g., Hyperliquid) for open positions and open orders. These residual positions/orders are tracked and appended to the new runtime snapshot under `residual_open_positions` and `residual_open_orders`. The service does NOT automatically close them; it relies on manual operator intervention or an explicit cleanup script to prevent unsafe automated unwinding.

### Feedback Consumer and DuckDB Persistence
The `rektslug-feedback-consumer` is also designed to fail closed.
- **Redis Disconnect:** The consumer attempts to reconnect indefinitely (with backoff) rather than crashing, ensuring it is always ready to receive feedback once the broker recovers.
- **DuckDB Unavailable:** If the `FeedbackDBService` cannot acquire a write lock on the DuckDB file, the consumer logs the failure and rejects the write path rather than blocking the Nautilus runtime. The report API returns `503` if it cannot measure `feedback_persisted`.
- **Retention/Reconciliation:** For bounded G3 evidence generation, the feedback consumer may be stopped briefly after a session closes so the reconciliation builder can read the feedback DuckDB without a writer lock. The service is then restarted immediately.
- **API Failure:** The `/signals/continuous-report` API will fail closed with a `503 Service Unavailable` if the DuckDB connection fails or if the `feedback_persisted` counter cannot be accurately measured.

## 5. Mismatch Visibility and NFR-002 (Async Boundary)

- **Publish/Persist Mismatches:** The continuous report exposes both `feedback_published` (from Nautilus) and `feedback_persisted` (from DuckDB). Any discrepancy is surfaced via `persistence_consistent=false`, `report_status="blocked"`, and a non-empty `blocking_issues` list.
- **NFR-002 (Non-blocking):** Nautilus only publishes feedback to Redis; it does not write DuckDB directly. The async boundary is the Redis channel itself, and the DuckDB write path lives in the separate `rektslug-feedback-consumer` service. Acceptance tests verify that the Nautilus event path reaches Redis publication without any DuckDB dependency in-process.
