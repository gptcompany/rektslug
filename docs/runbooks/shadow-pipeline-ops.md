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
