# Continuous Runtime Contracts

This document defines the public interfaces and contracts required for the `rektslug` and `nautilus_dev` continuous paper/testnet runtime (Spec-040).

## 1. Feedback Consumer Redis Contract

The `rektslug-feedback-consumer` service listens for real-time P&L feedback from Nautilus over Redis pub/sub.

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
    "residual_open_positions": 5,
    "residual_open_orders": 0
  }
  ```
  *(Note: `feedback_persisted` is derived directly from DuckDB rows whose `created_at` falls within the current session. The runtime snapshot must provide the remaining lifecycle counters and the `session_started_at` boundary.)*

- **Runtime snapshot source:**
  - Path from `HEATMAP_CONTINUOUS_RUNTIME_REPORT_PATH` or `CONTINUOUS_RUNTIME_REPORT_PATH`
  - Default fallback: `$(dirname HEATMAP_DB_PATH)/continuous_runtime_report.json`
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

### Compose Service Healthcheck
The `rektslug-feedback-consumer` container runs an internal healthcheck that validates:
1. The consumer process is running.
2. (Via `--healthcheck` flag) The DuckDB persistence layer has the required tables and write locks are correctly configured.
3. The Redis pub/sub connection is alive.
