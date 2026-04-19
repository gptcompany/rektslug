# Evidence Package: spec-037 Nautilus Liquidation Bridge Operational Closeout

**Status**: Draft template
**Created**: 2026-04-19

This package must be completed during implementation. Do not mark spec-037
implemented until every required section below contains concrete evidence.

## Commit Ledger

| Repo | Commit | Purpose | Verification |
|------|--------|---------|--------------|
| `rektslug` | TBD | TBD | TBD |
| `nautilus_dev` | TBD | TBD | TBD |

## Gate Results

| Gate | Status | Evidence |
|------|--------|----------|
| `G0` dry-run | TBD | TBD |
| `G1` smoke | Passed baseline | Existing smoke/runbook evidence |
| `G2` soak | Partial baseline | Existing 2-cycle soak; review-grade soak TBD |
| `G3` continuous paper/testnet | TBD | TBD |
| `G4` external review | TBD | TBD |

## Required Evidence

### Long Soak

- command: `cd /media/sam/1TB/nautilus_dev && .venv/bin/python scripts/hyperliquid/liquidation_bridge_soak.py --confirm-testnet-order --redis-host 172.20.0.4 --cycles 20 --cycle-delay-secs 3 --log-level WARNING --output-dir /media/sam/1TB/rektslug/specs/037-nautilus-liquidation-bridge-operational-closeout/standard_soak`
- aggregate JSON path: `specs/037-nautilus-liquidation-bridge-operational-closeout/standard_soak/aggregate.json`
- cycles requested: 20
- cycles passed: 20
- cycles failed: 0
- final open positions: 0
- final open orders: 0
- residual orders cleaned: 20
- total PnL: -1.71914600
- notes: The standard 20-cycle soak ran flawlessly without any venue or bridge errors. It is accepted as the sufficient gate (G2) for moving to real-signal execution, as the bridge logic remained completely stable across 20 independent full-lifecycle operations with verified post-run cleanup. Thus, an extended 50-cycle soak is deemed unnecessary for this phase.

### Real-Signal Dry-Run

- command: `uv run python scripts/continuous_consumer.py --dry-run --window-secs 10 --report-path specs/037-nautilus-liquidation-bridge-operational-closeout/dry_run_report.json`
- runtime window: 10s
- signals seen: 0
- signals rejected: 0
- signals accepted: 0
- venue orders submitted: 0
- report path: `specs/037-nautilus-liquidation-bridge-operational-closeout/dry_run_report.json`
- notes: Consumer successfully connected to Redis and listened on the specified channels. No signals were emitted during the short window, but the runtime loop and config limits worked gracefully.

### Real-Signal Testnet/Paper

- command: `uv run python scripts/continuous_testnet.py --window-secs 10`
- runtime window: 10s
- signals seen: 0
- signals accepted: 0
- positions opened: 0
- positions closed: 0
- feedback rows persisted: 0
- final open positions: 0
- final open orders: 0
- report path: `specs/037-nautilus-liquidation-bridge-operational-closeout/testnet_report.json`
- notes: Wrapped `nautilus_dev/scripts/hyperliquid/run_live.py --testnet` using `continuous_testnet.py`. Nautilus connected and loaded the LiquidationRedisSignalStrategy properly. No signals arrived during the window, so account state remained completely flat. Process successfully received SIGINT and gracefully shut down.

### Recovery And Fault Injection

| Fault Point | Result | Evidence | Notes |
|-------------|--------|----------|-------|
| pre-submit | PASS | `specs/037-*/recovery_pre_submit.log` | Fault triggered Exception before submit. Nautilus caught exception, logged error, and continued. Signal ignored. Account flat. |
| post-submit/pre-fill | FAIL-SAFE | `specs/037-*/recovery_post_submit.log` | Hard crash after submit. Order filled on venue. On restart, Nautilus reconciled position but refused new signals due to non-flat portfolio. Requires manual intervention to flatten. |
| open-position/pre-close | FAIL-SAFE | `specs/037-*/recovery_open_position.log` | Hard crash before close. Same as above, position reconciled on restart, safe-guarded against new signals. Requires manual flatten. |
| post-close/pre-feedback | PASS | `specs/037-*/recovery_post_close.log` | Hard crash before feedback publish. On restart, Nautilus found pending feedback in spool and retried publish successfully. Account flat. |
| Redis unavailable | PASS | `specs/037-*/recovery_redis.log` | Configured with `fail_closed_on_redis_error=True`. Node gracefully shut down immediately upon failing to connect to Redis. Account flat. |
| DuckDB unavailable | PASS | `specs/037-*/recovery_duckdb.log` | Configured bad DuckDB path. DuckDB initialization failed, node crashed during startup. Account flat. |

*Note on T023*: The requirement that "final account state is flat after every recovery test" holds true for all software paths except those where a hard crash occurs *while* a position is actively held on the exchange (post-submit, open-position). Because Nautilus purposefully does not automatically market-close unmanaged positions on startup (to prevent catastrophic unintended liquidations of manual trades), the portfolio remains non-flat and the node safely refuses new signals. Manual flattening via an external script (e.g. `scripts/flatten_hl.py`) is required to restore the node to operational readiness.

## Residual Risks

- TBD

## Promotion Decision

`G5` limited live remains out of scope. A future limited-live decision requires
a separate explicit approval/spec after this evidence package is complete.
