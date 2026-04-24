# Nautilus Dev Unified Cockpit Runtime

Use this runbook when the unified operator cockpit is blocked even though the
`rektslug` provider is healthy.

## Symptoms

- `rektslug` ops endpoints are healthy
- unified cockpit still shows `BLOCKED` or `DEGRADED`
- local blockers mention:
  - `nautilus_runtime`
  - `canonical_order_flow`
  - `risk_controls`
  - `tcp_ip_interfaces`
  - `strategic_controller`
  - `evolution_governance`

This usually means local `nautilus_dev/runtime/*.json` artifacts are stale or
reflect stopped processes.

## Immediate Recovery

Refresh L3:

```bash
cd /media/sam/1TB/nautilus_dev
dotenvx run -f /media/sam/1TB/.env -- \
  uv run python scripts/portfolio/run_strategic_controller.py \
  --project-root . \
  --duration-secs 180 \
  --poll-interval-secs 10 \
  --enable-evolution-gate \
  --enable-performance-evaluator \
  --enable-oos-integrator
```

Refresh L2:

```bash
cd /media/sam/1TB/nautilus_dev
dotenvx run -f /media/sam/1TB/.env -- \
  uv run python scripts/hyperliquid/run_continuous.py \
  --mode testnet \
  --symbol BTCUSDT_COCKPIT_UNIFIED4 \
  --instrument BTC-USD-PERP.HYPERLIQUID \
  --redis-host 127.0.0.1 \
  --redis-port 6379 \
  --window-secs 900 \
  --runtime-snapshot-path runtime/portfolio-runtime-snapshot.json \
  --runtime-ledger-path runtime/portfolio-runtime-ledger.jsonl \
  --control-state-path runtime/operator-control-state.json \
  --connectivity-status-path runtime/operator-connectivity-status.json \
  --risk-status-path runtime/operator-risk-status.json \
  --error-registry-path runtime/operator-error-registry.jsonl
```

Important:

- do not use `/var/lib/rektslug-db/*` for local `nautilus_dev` cockpit artifacts
- do not use `run_strategic_controller.py --once` if you need a sustained green
  cockpit

## Healthy Verification

Run:

```bash
cd /media/sam/1TB/nautilus_dev
dotenvx run -f /media/sam/1TB/.env -- uv run python - <<'PY'
from pathlib import Path
from operator_cockpit.api import build_browser_state
import json

payload = build_browser_state(
    project_root=Path('.'),
    rektslug_base_url='http://127.0.0.1:8002',
    catastrophe_drill_passed=True,
    restart_clean=True,
)

print(json.dumps({
    'overall_status': payload.get('overall_status'),
    'readiness_ready': payload.get('readiness', {}).get('ready'),
    'blocking_card_ids': payload.get('readiness', {}).get('details', {}).get('blocking_card_ids'),
    'critical_blockers': payload.get('readiness', {}).get('critical_blockers'),
}, indent=2, sort_keys=True, default=str))
PY
```

Expected:

```json
{
  "overall_status": "HEALTHY",
  "readiness_ready": true,
  "blocking_card_ids": [],
  "critical_blockers": []
}
```

## Permanent Fix

Promote the two commands above into persistent host-managed services in
`nautilus_dev`:

- continuous Nautilus runtime service
- strategic-controller runtime service

The detailed service handoff is tracked in:

- [NAUTILUS_DEV_RUNTIME_PERSISTENCE_HANDOFF.md](/media/sam/1TB/rektslug/specs/040-nautilus-continuous-paper-testnet/NAUTILUS_DEV_RUNTIME_PERSISTENCE_HANDOFF.md)
