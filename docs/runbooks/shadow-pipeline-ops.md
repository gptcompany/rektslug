# Shadow Pipeline Operations Runbook

## Start

```bash
docker compose up -d redis rektslug-shadow-producer rektslug-shadow-consumer
```

## Stop

```bash
docker compose stop rektslug-shadow-producer rektslug-shadow-consumer
```

## Check Status

```bash
# Service health
docker compose ps | grep shadow

# Producer logs (last cycle)
docker logs rektslug-shadow-producer --tail 50

# Consumer logs
docker logs rektslug-shadow-consumer --tail 50

# Redis connectivity
docker exec rektslug-redis redis-cli ping

# Latest report
docker exec rektslug-shadow-consumer cat /var/lib/rektslug-db/shadow_report.json | python3 -m json.tool
```

## Troubleshooting

### Producer stuck / no output
1. Check if HL node is reachable: `curl -sf http://localhost:3001/info -d '{"type":"meta"}' | head -c 100`
2. Check ABCI anchor freshness: `ls -lt /media/sam/4TB-NVMe/docker-volumes/hyperliquid/hl/data/periodic_abci_states/$(date +%Y%m%d)/ | head -3`
3. Check producer env: `docker exec rektslug-shadow-producer env | grep HEATMAP`

### Consumer not receiving signals
1. Check Redis: `docker exec rektslug-redis redis-cli PUBSUB CHANNELS`
2. Check REDIS_HOST env: `docker exec rektslug-shadow-consumer env | grep REDIS`

### WebSocket Stream Issues
1. Verify WS connection logs: `docker logs rektslug-shadow-consumer | grep -i "connected to"`
2. Verify WS message processing: `docker logs rektslug-shadow-consumer | grep -i "event"`
3. Check for disconnection errors: `docker logs rektslug-shadow-consumer | grep -i "error"`

### Correlation / Validation Monitoring
1. Check correlation matches count: `docker exec rektslug-shadow-consumer jq .summary.correlation_matches /var/lib/rektslug-db/shadow_report.json`
   - If `0` for over 24h, check if `--enable-ws-stream` is active and WS stream is healthy.
2. Verify shadow PnL generation: `docker exec rektslug-shadow-consumer jq .calibration.total_pnl /var/lib/rektslug-db/shadow_report.json`

### Stale Stream / Alerting Thresholds
- **Report Freshness**: If `/var/lib/rektslug-db/shadow_report.json` is older than `REKTSLUG_SHADOW_INTERVAL_SECONDS` + 60s, the consumer might be stalled. Use `find` to check: `find /var/lib/rektslug-db -name 'shadow_report.json' -mmin -10`.
- **Alerting**: The circuit breaker automatically publishes alerts to `liquidation:alerts:{symbol}` on Redis when drawdown limits (`cb-max-drawdown`) are breached. Monitor this channel for automated trip notifications.

### Change interval
```bash
# In .env:
REKTSLUG_SHADOW_INTERVAL_SECONDS=600  # 10 min

# Restart producer only
docker compose restart rektslug-shadow-producer
```

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `REKTSLUG_SHADOW_INTERVAL_SECONDS` | 300 | Snapshot interval (seconds) |
| `HEATMAP_HYPERLIQUID_INFO_FALLBACK_URLS` | public API | HL Info endpoints (comma-separated, priority order) |
| `REDIS_HOST` | localhost | Redis hostname (set to `redis` in compose) |
| `REDIS_PORT` | 6379 | Redis port |
