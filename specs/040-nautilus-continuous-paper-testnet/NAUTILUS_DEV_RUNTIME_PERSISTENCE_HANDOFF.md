# nautilus_dev Runtime Persistence Handoff

Last verified: 2026-04-24

This handoff closes the remaining operational gap after `rektslug` stopped
blocking the unified operator cockpit.

## Verified Facts

The unified cockpit went `HEALTHY` only when both local `nautilus_dev` runtime
layers were live at the same time:

- L2 continuous Nautilus runtime: `RUNNING`
- L3 strategic controller: `RUNNING`
- `rektslug /ops/summary`: `HEALTHY`
- `rektslug /ops/continuous-report`: `HEALTHY`
- `rektslug /ops/evidence/spec-040/latest`: `HEALTHY`

Observed unified builder result:

```json
{
  "overall_status": "HEALTHY",
  "readiness_ready": true,
  "blocking_card_ids": [],
  "critical_blockers": [],
  "provider_blockers": []
}
```

Important contract note:

- the raw `build_browser_state(...)` payload does not currently expose a
  top-level `paper_ready`
- the browser/UI derives that flag from `readiness.ready`
- therefore the correct success check is `readiness.ready == true`

## Root Cause Of The Previous Local Block

The remaining blocker was not `rektslug`.

The unified gate was stale because the local `nautilus_dev` artifacts were not
being kept fresh:

- `runtime/portfolio-runtime-snapshot.json` could fall back to `STOPPED`
- `runtime/operator-connectivity-status.json` could fall back to `STOPPED`
- `runtime/operator-risk-status.json` could fall back to `DEGRADED`
- `runtime/strategic-controller-status.json` could be rewritten as `STOPPED`
  when the controller was run only with `--once`

Two specific operational facts mattered:

1. `scripts/hyperliquid/run_continuous.py` defaults
   `--runtime-snapshot-path` to `/var/lib/rektslug-db/continuous_runtime_report.json`,
   which is wrong for the local `nautilus_dev` cockpit path unless explicitly
   overridden.
2. `scripts/portfolio/run_strategic_controller.py --once` is useful for a
   heartbeat refresh, but it leaves the canonical L3 status artifact with
   `status=STOPPED` after exit. That cannot sustain a green cockpit.

## Required Persistent Processes

Two local services need to stay alive.

### 1. Continuous Nautilus L2 Runtime

Command shape that worked:

```bash
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

Required invariants:

- use local `runtime/*` artifact paths
- do not rely on `/var/lib/rektslug-db/*` for local cockpit ownership
- keep the process alive long enough that the builder sees `node_status=RUNNING`
  and fresh L1/L2 artifacts

### 2. Strategic Controller L3 Runtime

Command shape that worked:

```bash
dotenvx run -f /media/sam/1TB/.env -- \
  uv run python scripts/portfolio/run_strategic_controller.py \
  --project-root . \
  --duration-secs 180 \
  --poll-interval-secs 10 \
  --enable-evolution-gate \
  --enable-performance-evaluator \
  --enable-oos-integrator
```

Required invariants:

- do not use `--once` for sustained cockpit readiness
- keep `runtime/strategic-controller-status.json` fresh and `status=RUNNING`
- keep evolution governance configured and running

## Recommended systemd Ownership

These should become host-managed services in `nautilus_dev`.

Suggested units:

- `nt-liquidation-continuous.service`
- `nt-strategic-controller.service`

Recommended characteristics:

- `Restart=always`
- `RestartSec=5`
- `WorkingDirectory=/media/sam/1TB/nautilus_dev`
- `EnvironmentFile` or `dotenvx run -f /media/sam/1TB/.env -- ...`
- explicit local `runtime/*` paths for L2 artifacts
- no `--once` mode for L3

## Acceptance Checks

### Local artifact checks

`runtime/portfolio-runtime-snapshot.json`:

- `node_status == RUNNING`
- `risk.entries_enabled == true`
- `risk.redis_connected == true`
- fresh `generated_at` / `heartbeat_at`

`runtime/operator-connectivity-status.json`:

- `status == HEALTHY`
- `details.redis.status == UP`
- `details.message_bus.status == UP`
- `details.venues.hyperliquid.status == UP`
- `details.venues.hyperliquid.ws == UP`
- `details.bridges.liquidation_bridge == UP`

`runtime/operator-risk-status.json`:

- `status in {ACTIVE, HEALTHY}`
- `entries_enabled == true`
- `reduce_only == false`
- `circuit_breaker == ACTIVE`

`runtime/strategic-controller-status.json`:

- `status == RUNNING`
- `details.is_running == true`
- `details.evolution_gate_running == true`
- `details.performance_evaluator_configured == true`
- `details.oos_integrator_configured == true`

### Unified builder check

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
    'provider_blockers': payload.get('readiness', {}).get('details', {}).get('provider_blockers'),
}, indent=2, sort_keys=True, default=str))
PY
```

Expected healthy result:

```json
{
  "overall_status": "HEALTHY",
  "readiness_ready": true,
  "blocking_card_ids": [],
  "critical_blockers": [],
  "provider_blockers": []
}
```

## Non-Goals

- no new UI in `rektslug`
- no operator controls in `rektslug`
- no new gate ownership in `rektslug`
- no merging of browser payloads client-side

`rektslug` remains a read-only state/report provider.
