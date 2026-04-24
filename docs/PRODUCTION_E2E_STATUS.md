# rektslug Production E2E Status

Last verified: 2026-04-24

`rektslug` is an enabled end-to-end production service. Treat this repository as
the production owner for data sync, API serving, Hyperliquid shadow validation,
historical snapshot backfill, automated health monitoring, and execution
feedback persistence/reporting for the continuous paper/testnet runtime.

## Enabled Runtime

The production runtime is split across Docker services and host systemd timers.

### Docker Compose

- `rektslug-api`: FastAPI core service and dashboard/API surface.
- `rektslug-sync`: near-real-time Parquet -> QuestDB gap-fill worker.
- `redis`: internal pub/sub bus for signal transport.
- `rektslug-shadow-producer`: Hyperliquid snapshot producer and Redis signal publisher.
- `rektslug-shadow-consumer`: shadow-mode signal consumer with WebSocket liquidation stream correlation, circuit breaker checks, and report persistence.
- `rektslug-feedback-consumer`: execution feedback persistence service consuming
  `liquidation:feedback:{symbol}` and writing to dedicated
  `signal_feedback.duckdb`.

Start or refresh the Docker runtime:

```bash
docker compose up -d --build
docker compose ps
```

### Systemd Timers

- `lh-ingestion.timer`: daily DuckDB ingestion.
- `lh-ccxt-gap-fill.timer`: near-real-time ccxt gap fill.
- `lh-hl-backfill-monitor.timer`: hourly Hyperliquid backfill batch health check.

Install or refresh host timers:

```bash
sudo ./scripts/systemd/install.sh
systemctl list-timers lh-ingestion.timer lh-ccxt-gap-fill.timer lh-hl-backfill-monitor.timer --no-pager
```

## Verified Evidence

## Current Operational Status

The runtime is currently healthy on the `rektslug` side. The remaining risk is
data freshness from external vendor-fed inputs, not internal Docker/service
wiring.

### Green

- `rektslug-api`
- `rektslug-sync`
- `redis`
- `rektslug-shadow-producer`
- `rektslug-shadow-consumer`
- `rektslug-feedback-consumer`
- `aggTrades`
- `klines`
- `metrics`

### Yellow

- `open_interest`
- `ccxt -> QuestDB gap fill`
- continuous signal/execution/feedback quality as a whole

These lanes are structurally healthy on the `rektslug` side, but their final
freshness still depends on upstream vendor feeds.

### Red / Yellow

- `funding_rate`

This lane is correct structurally, but should be treated as degraded whenever
the upstream `ccxt-data-pipeline` source is stale.

### Hyperliquid Shadow Producer Recovery

The Hyperliquid producer was restored on 2026-04-24 after repeated OOM-driven
failures under the old 2 GiB limit.

Observed recovered state:

- container `healthy`
- `OOMKilled=false`
- `RestartCount=0`
- fresh manifests for `BTCUSDT` and `ETHUSDT`
- successful Redis publish for both symbols

Observed post-fix shadow summary:

```json
{
  "signals_seen": 20,
  "accepted": 10,
  "rejected": 10,
  "accept_rate": 0.5
}
```

### Residual Debt: Hyperliquid ABCI Decoder Memory

This is not a current blocker, but it is still open technical debt.

Current state:

- the producer is operational again
- the old `2 GiB` limit was not sufficient
- the producer currently runs with a `6 GiB` container memory limit

What remains inefficient:

- the ABCI anchor decode/reconstruction path still carries a large working set
- the current mitigation restores service health, but it does so with RAM headroom
  rather than a fully optimized decoder path

Why this is not a spec-sized item right now:

- no public contract changed
- no runtime boundary changed
- no product scope changed
- the service is already restored and verified

What would make it spec-worthy later:

- a redesign of the Hyperliquid anchor decode path
- a change in sidecar/export contracts
- a broader replay/reconstruction architecture change

Current optimization target:

- reduce peak memory enough to bring `rektslug-shadow-producer` back toward a
  smaller runtime envelope without regressing correctness

### Continuous Paper/Testnet Runtime

`spec-040` is now closed with retained real G3 evidence.

Retained session:

- `specs/040-nautilus-continuous-paper-testnet/g3_session/20260422T212929Z/`

Observed retained counters:

```json
{
  "signals_seen": 1,
  "signals_accepted": 1,
  "positions_opened": 1,
  "positions_closed": 1,
  "feedback_published": 1,
  "feedback_persisted": 1,
  "report_status": "ok",
  "gate_status": "READY_FOR_REVIEW"
}
```

Runtime boundary for this lane remains explicit:

- `rektslug`: signal production, Redis contracts, feedback persistence, reporting
- `nautilus_dev`: continuous Nautilus execution runtime on testnet

Unified cockpit note:

- `rektslug` is no longer the blocker for unified cockpit readiness
- the remaining steady-state requirement is persistent L2/L3 runtime ownership in
  `nautilus_dev`
- the verified persistence handoff is tracked in:
  `specs/040-nautilus-continuous-paper-testnet/NAUTILUS_DEV_RUNTIME_PERSISTENCE_HANDOFF.md`

### Hyperliquid Backfill Monitor

The Hyperliquid backfill monitor was installed and validated through real
systemd, not only through local script execution.

Observed systemd result on 2026-04-21:

```json
{
  "ok": true,
  "batch_path": "/media/sam/1TB/rektslug/data/validation/expert_snapshots/hyperliquid/batches/backfill_hyperliquid_20260414T000000Z_20260421T000000Z_60m.json",
  "status": "completed",
  "results_count": 24,
  "errors": []
}
```

The current 7d Hyperliquid batch record contains:

```json
{
  "results_count": 24,
  "requested_slots": 169,
  "anchors_used_total": 24,
  "anchor_resolution_failures_total": 145,
  "coverage": {
    "BTCUSDT": {"success": 24, "partial": 0, "gap": 0, "failure": 0, "skipped": 0},
    "ETHUSDT": {"success": 24, "partial": 0, "gap": 0, "failure": 0, "skipped": 0}
  }
}
```

## Operational Checks

Use these commands when validating the production state:

```bash
docker compose ps
systemctl status lh-hl-backfill-monitor.timer --no-pager
journalctl -u lh-hl-backfill-monitor.service -n 80 --no-pager
scripts/run-hl-backfill-monitor.sh
```

For the shadow pipeline:

```bash
docker logs rektslug-shadow-producer --tail 50
docker logs rektslug-shadow-consumer --tail 80
docker exec rektslug-shadow-consumer jq .summary /var/lib/rektslug-db/shadow_report.json
```

For the continuous paper/testnet runtime evidence:

```bash
cat specs/040-nautilus-continuous-paper-testnet/g3_session/20260422T212929Z/session_result.json
cat specs/040-nautilus-continuous-paper-testnet/g3_session/20260422T212929Z/evidence/summary.json
```

## Production Boundary

`rektslug` is production-enabled for signal production, API serving, shadow
validation, backfill, monitoring, and execution-feedback persistence/reporting.
Downstream execution systems such as NT Trader or Nautilus must still provide
their own execution runtime and venue evidence before any live trading claim is
made.

Do not describe partial wiring as complete. A production-green state must be
backed by concrete output from Docker, systemd, tests, or persisted reports.
