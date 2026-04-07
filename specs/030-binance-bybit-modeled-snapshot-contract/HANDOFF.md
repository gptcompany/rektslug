# Modeled Snapshot Contract Handoff (spec-030)

## Overview
This document describes how to consume the artifacts produced under the `spec-030` contract for Binance and Bybit.

## Layout
All artifacts are written to `data/validation/modeled_snapshots/{exchange}/`.

```text
data/validation/modeled_snapshots/{exchange}/
├── artifacts/
│   └── {symbol}/
│       └── {snapshot_ts}/
│           ├── binance_standard.json
│           └── binance_depth_weighted.json
├── manifests/
│   └── {symbol}/
│       └── {snapshot_ts}.json
└── batches/
    └── {batch_id}.json
```

## Manifest Schema
The manifest is the authoritative entry point for any `snapshot_ts`. It lists all available models and their status.

```json
{
  "exchange": "binance",
  "snapshot_ts": "2026-04-07T12:00:00Z",
  "distribution_normalization": "normalized",
  "models": {
    "binance_standard": {
      "model_id": "binance_standard",
      "availability_status": "available",
      "source_metadata": { ... },
      "artifact_path": "artifacts/BTCUSDT/2026-04-07T12:00:00Z/binance_standard.json"
    },
    "binance_depth_weighted": {
      "model_id": "binance_depth_weighted",
      "availability_status": "blocked_source_missing",
      "source_metadata": { ... }
    }
  }
}
```

## Model Channels
1. **binance_standard / bybit_standard**: Statistical aggregate using OI + aggTrades + Exchange MMR tiers.
2. **binance_depth_weighted / depth_weighted**: LOB-aware model that weights liquidation clusters by orderbook depth (thin book = higher weight).

## Determinism & Provenance
Each artifact contains `source_metadata.input_identity` which pins the exact source files and timestamps used. Re-running the producer for the same `snapshot_ts` with the same inputs will produce identical `long_distribution` and `short_distribution` (serialized as float64).

## Consumption
1. Locate the manifest for the desired `exchange`, `symbol`, and `snapshot_ts`.
2. Check `availability_status` for the desired `model_id`.
3. If `available`, fetch the artifact from `artifact_path` (relative to the exchange root).
4. Parse `long_distribution` and `short_distribution` as price-bucket maps.
