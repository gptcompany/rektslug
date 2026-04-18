# Nautilus Liquidation Bridge Live Smoke

Date: 2026-04-18

## Purpose

This runbook verifies the operational loop between `rektslug` and the Nautilus
runtime on Hyperliquid testnet:

1. `rektslug` publishes a liquidation signal to Redis.
2. Nautilus consumes the signal through `LiquidationRedisSignalStrategy`.
3. Nautilus submits and closes a tiny Hyperliquid testnet position.
4. Nautilus publishes realized trade feedback back to Redis.
5. `rektslug` persists the feedback into DuckDB.
6. The account is verified flat with no open orders.

The smoke is intentionally testnet-only and intentionally guarded.

## Relevant Commits

`rektslug`:

- `77b70fa nautilus: add redis feedback publisher bridge`
- `9d11404 nautilus: track signal lifecycle for feedback publication`

`nautilus_dev`:

- `3e3b97e liquidation-bridge: harden live node execution path`
- `5f59d5e liquidation-bridge: add guarded testnet smoke`

## Preconditions

- Python 3.12 Nautilus environment is available in `nautilus_dev`.
- Redis is reachable from the host.
- `HYPERLIQUID_TESTNET_PK` exists in dotenvx or the parent environment.
- The key must be funded on Hyperliquid testnet.
- Do not enable shell tracing while loading secrets.

The smoke does not print the private key. It prints only a shortened public
address label.

## Command

Single-cycle smoke using dotenvx without exposing the key:

```bash
set +x
pk="$(dotenvx get HYPERLIQUID_TESTNET_PK -f /media/sam/1TB/nautilus_dev/.env 2>/dev/null)"
export HYPERLIQUID_TESTNET_PK="$pk"
unset pk

cd /media/sam/1TB/nautilus_dev
.venv/bin/python scripts/hyperliquid/liquidation_bridge_smoke.py \
  --confirm-testnet-order \
  --redis-host 172.20.0.4
```

Short sequential soak:

```bash
set +x
pk="$(dotenvx get HYPERLIQUID_TESTNET_PK -f /media/sam/1TB/nautilus_dev/.env 2>/dev/null)"
export HYPERLIQUID_TESTNET_PK="$pk"
unset pk

cd /media/sam/1TB/nautilus_dev
.venv/bin/python scripts/hyperliquid/liquidation_bridge_soak.py \
  --confirm-testnet-order \
  --redis-host 172.20.0.4 \
  --cycles 2 \
  --cycle-delay-secs 3 \
  --log-level WARNING \
  --output-dir /tmp/nautilus_liquidation_bridge_soak_codex
```

The `--confirm-testnet-order` flag is required for both scripts. Without it,
the scripts exit before placing any order.

## Expected Success Output

The run must end with:

```text
NODE_SMOKE_OK
```

The `NODE_SMOKE_RESULT` payload must show:

```text
'entry_submitted': True
'opened': True
'close_submitted': True
'closed': True
'feedback_seen': True
'feedback_rows': 1
'open_positions': 0
'open_orders': 0
'errors': []
```

The result row should contain:

- `symbol`: expected signal symbol, usually `BTCUSDT`
- `signal_id`: generated `node-smoke-*` id
- `entry_price`: actual testnet fill price
- `exit_price`: actual testnet close price
- `pnl`: realized testnet PnL after fees/slippage
- `source`: `nautilus`

## Latest Verified Evidence

Latest scripted smoke:

- `signal_id`: `node-smoke-1776539448`
- `symbol`: `BTCUSDT`
- `entry_price`: `75953.00000000`
- `exit_price`: `75922.00000000`
- `pnl`: `-0.09934200`
- `source`: `nautilus`
- `feedback_rows`: `1`
- `residual_reduce_only_orders_canceled`: `1`
- final `open_positions`: `0`
- final `open_orders`: `0`

Latest short sequential soak:

- `cycles`: `2`
- `passed_cycles`: `2`
- `failed_cycles`: `0`
- `final_open_positions`: `0`
- `final_open_orders`: `0`
- `total_pnl`: `-0.14259500`
- `final_account_value`: `498.813527`
- aggregate report:
  `/tmp/nautilus_liquidation_bridge_soak_codex/aggregate.json`

Cycle evidence:

- cycle 1: `node-smoke-1776541001`, `feedback_rows=1`, `pnl=-0.07029700`
- cycle 2: `node-smoke-1776541059`, `feedback_rows=1`, `pnl=-0.07229800`

Earlier manual smoke before script hardening:

- `signal_id`: `node-smoke-1776520197`
- `symbol`: `BTCUSDT`
- `entry_price`: `76284.00000000`
- `exit_price`: `76224.00000000`
- `pnl`: `-0.12862700`
- `source`: `nautilus`

## Safety Notes

- The script places a real testnet market entry and a real reduce-only market
  close for the configured size.
- The default size is `0.001` BTC.
- The script performs post-run account checks and cancels residual reduce-only
  orders for the smoke coin unless `--skip-residual-order-cleanup` is passed.
- A non-zero count in `open_positions` or `open_orders` is a failed smoke.
- A missing feedback row is a failed smoke even if the exchange lifecycle
  completed.
- The soak runner invokes the guarded smoke as a subprocess per cycle. This is
  intentional: it validates restart, reconciliation, cleanup, feedback
  persistence, and account flatness repeatedly.

## Review Interpretation

This smoke proves the live operational contract:

`rektslug signal -> Redis -> Nautilus strategy -> Hyperliquid testnet -> Redis feedback -> rektslug DuckDB`

It does not prove production profitability, signal calibration, or mainnet
safety. Those remain separate gates.

## Blockers For Promotion

Do not promote beyond testnet/paper if any of these are true:

- `NODE_SMOKE_OK` is absent.
- `feedback_rows != 1`.
- `open_positions != 0`.
- `open_orders != 0`.
- `errors` is non-empty.
- Redis feedback is received but DuckDB persistence fails.
- The launcher requires manual code edits to start.
