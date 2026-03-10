# Spec 018: Provider Liq-Heat-Map Comparison

## Overview

Operationalize a repeatable comparison workflow for **liq-heat-map only** across:

- local `rektslug` CoinAnk-style heat-map route
- CoinAnk `liq-heat-map`
- Coinglass heatmap-style liquidation endpoints

This spec is intentionally separate from `spec-017`:

- `spec-017` = `liq-map` only
- `spec-018` = `liq-heat-map` only

## Scope

### In Scope

- product: `liq-heat-map` only
- symbols: `BTCUSDT`, `ETHUSDT`
- timeframes/windows: `48h`, `7d`
- local vs CoinAnk vs Coinglass capture and comparison
- raw payload artifacts, screenshots, normalized reports, manifests

### Out of Scope

- `liq-map` workflows (already covered by `spec-017`)
- liquidity heatmap products not tied to liquidation heatmap parity
- symbols beyond BTC/ETH
- windows beyond `48h` and `7d`

## Reference Routes

### Local / CoinAnk

- Local BTC 48h: `http://localhost:8002/chart/derivatives/liq-heat-map/btcusdt/48h`
- Local BTC 7d: `http://localhost:8002/chart/derivatives/liq-heat-map/btcusdt/7d`
- Local ETH 48h: `http://localhost:8002/chart/derivatives/liq-heat-map/ethusdt/48h`
- Local ETH 7d: `http://localhost:8002/chart/derivatives/liq-heat-map/ethusdt/7d`
- CoinAnk BTC 48h: `https://coinank.com/chart/derivatives/liq-heat-map/btcusdt/48h`
- CoinAnk BTC 7d: `https://coinank.com/chart/derivatives/liq-heat-map/btcusdt/7d`
- CoinAnk ETH 48h: `https://coinank.com/chart/derivatives/liq-heat-map/ethusdt/48h`
- CoinAnk ETH 7d: `https://coinank.com/chart/derivatives/liq-heat-map/ethusdt/7d`

### Coinglass

Use the endpoints already documented in repo for liquidation heatmap payloads.
Only captures that normalize to the `liq-heat-map` product are valid for this spec.

## Functional Requirements

- **FR-001**: The workflow MUST compare only `liq-heat-map` artifacts.
- **FR-002**: The workflow MUST reject `liq-map` artifacts when running in `spec-018` mode.
- **FR-003**: The workflow MUST support only BTC/ETH and `48h`/`7d`.
- **FR-004**: Every run MUST persist raw provider captures and screenshots in timestamped artifact directories.
- **FR-005**: Every run MUST emit a manifest with symbol, window, provider URLs, capture mode, and product tags.
- **FR-006**: Every run MUST emit a normalized report including local/CoinAnk/Coinglass structural parity checks.
- **FR-007**: Gap-analysis output MUST be aligned to heatmap-style structures, not price-bin liq-map structures.

## Non-Functional Requirements

- **NFR-001**: One matrix entry SHOULD complete in under 90 seconds.
- **NFR-002**: Full 4-entry baseline matrix SHOULD complete in under 15 minutes.
- **NFR-003**: Artifacts MUST be reproducible and auditable from manifest metadata alone.

## Edge Cases

- provider returns empty heatmap arrays
- provider returns liq-map payload at a heatmap URL (wrong product)
- local heatmap endpoint temporarily unavailable during sync gap-fill
- Coinglass encoded payload format drift

## Success Criteria

- **SC-001**: A single command can run any one supported `(symbol, window)` pair and produce complete artifacts.
- **SC-002**: Full matrix baseline (`BTC/ETH x 48h/7d`) is captured with valid heatmap-only product tags.
- **SC-003**: Reports make provider-side structural mismatches explicit without mixing in liq-map datasets.
- **SC-004**: The workflow is repeatable without manual artifact renaming or ad-hoc parsing.

## Notes

- Runtime prerequisites from `spec-016` still apply (`rektslug-api`, `rektslug-sync`, DuckDB freshness).
- Provider credentials continue to be loaded via `dotenvx` (`COINANK_*`, `COINGLASS_*`).
