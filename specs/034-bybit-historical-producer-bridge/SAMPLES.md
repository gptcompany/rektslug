# Samples: spec-034 Bybit Historical Producer Bridge

This directory contains a retained sample historical Bybit bridge run under:

- `samples/bybit_historical_output/source/`: raw historical + metrics downloader inputs
- `samples/bybit_historical_output/normalized/`: producer-readable normalized parquet outputs
- `samples/bybit_historical_output/output/bybit/artifacts/`: modeled snapshot artifacts
- `samples/bybit_historical_output/output/bybit/manifests/`: retained historical manifest

Reference sample window:
- symbol: `BTCUSDT`
- date: `2024-01-01`
- snapshot_ts: `2024-01-01T12:00:00Z`

Included retained outputs:
- `bybit_standard` manifest coverage
- `depth_weighted` manifest coverage
- normalized orderbook parquet in producer-readable wide schema
- normalization metadata with source path, digest, version, and row count

Determinism evidence:
- `tests/test_bybit_historical_bridge.py`
- `tests/test_bybit_modeled_snapshot_producer.py`
