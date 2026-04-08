# spec-031 Handoff

## Summary

`spec-031` is the serving-layer follow-up to `spec-030`.

It formalizes and implements:

- Binance public CoinAnK-style liq-map serving
- Bybit public CoinAnK-style liq-map serving

It does **not** unify Hyperliquid under the same public endpoint.

## Implemented

- `/liquidations/coinank-public-map` accepts `exchange`
- `CoinankPublicMapResponse` includes `exchange`
- Binance and Bybit public requests use the same response family
- Binance prefers artifact-backed serving and retains the legacy fallback path
- Bybit serves from `spec-030` artifacts and fails explicitly if no usable artifact exists
- Bybit CoinAnK-style frontend routes pass `exchange` into the unified public endpoint
- Hyperliquid remains on `/liquidations/hl-public-map`
- Reader selection now prefers the latest compatible available artifact, not just the newest manifest
- Timeframe semantics are documented as serving/presentation semantics for artifact-backed responses until producer artifacts become timeframe-addressable

## Explicitly Out of Scope

- Hyperliquid support through `/liquidations/coinank-public-map`
- Hyperliquid variant unification
- Expansion of `spec-030` producer responsibilities beyond compatibility fixes

## Validation Snapshot

- `tests/test_modeled_snapshot_export_layout.py` covers exchange-root artifact/manifest lookup and latest-available reader semantics
- `tests/integration/test_bybit_public_map.py` verifies Binance and Bybit public route behavior

## Architectural Note

The earlier local draft mixed together:

- `spec-030` producer/export work
- `spec-031` serving work
- Hyperliquid ideas that were not actually implemented on the unified path

This handoff fixes that boundary. `spec-031` should be read as a Binance/Bybit public-serving spec layered on top of `spec-030`.
