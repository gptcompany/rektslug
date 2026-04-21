# rektslug Production E2E Status

Last verified: 2026-04-21

`rektslug` is an enabled end-to-end production service. Treat this repository as
the production owner for data sync, API serving, Hyperliquid shadow validation,
historical snapshot backfill, and automated health monitoring.

## Enabled Runtime

The production runtime is split across Docker services and host systemd timers.

### Docker Compose

- `rektslug-api`: FastAPI core service and dashboard/API surface.
- `rektslug-sync`: near-real-time Parquet -> QuestDB gap-fill worker.
- `redis`: internal pub/sub bus for signal transport.
- `rektslug-shadow-producer`: Hyperliquid snapshot producer and Redis signal publisher.
- `rektslug-shadow-consumer`: shadow-mode signal consumer with WebSocket liquidation stream correlation, circuit breaker checks, and report persistence.

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

## Production Boundary

`rektslug` is production-enabled for signal production, API serving, shadow
validation, and monitoring. Downstream execution systems such as NT Trader or
Nautilus must consume `rektslug` APIs/signals and provide their own execution
evidence before any live trading claim is made.

Do not describe partial wiring as complete. A production-green state must be
backed by concrete output from Docker, systemd, tests, or persisted reports.
