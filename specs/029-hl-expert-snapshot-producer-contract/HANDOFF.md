# Producer/Consumer Handoff Contract (Phase 7)

## Overview
This document serves as the handoff reference for consumers (e.g., `nautilus_dev`) reading Hyperliquid expert snapshots exported by `rektslug`.

## Export Layout

The export directory root is `data/validation/expert_snapshots/hyperliquid/`.

### 1. Manifests (`manifests/{symbol}/{snapshot_ts}.json`)
Consumers MUST start by reading the manifest. The manifest acts as the source of truth for a given evaluation point.
*   **Format**: JSON. Use `json.load()` without importing any internal `rektslug` modules.
*   **Key Guarantee**: All five expert channels (`v1`, `v2`, `v3`, `v4`, `v5`) are ALWAYS explicitly listed in the manifest.
*   **Availability**: Check `availability_status`. Valid values are `available`, `missing`, `failed_decode`, `not_built`.
*   **Paths**: If an artifact is available, its relative path is provided in `artifact_path` (e.g., `artifacts/BTCUSDT/2026-04-03T12:00:00Z/v1.json`).

### 2. Artifacts (`artifacts/{symbol}/{snapshot_ts}/{expert_id}.json`)
Artifacts contain the actual bucketed distributions.
*   **Precision**: `float64` is enforced for reference prices, bucket grid values, and distribution volumes.
*   **Grid**: The artifact will declare the grid form. MVP grid form relies on explicit `min_price`, `max_price`, and `step` (all `float64`).
*   **Data References**: Exported artifacts DO NOT contain any references to local `data/cache/` paths, ensuring safe consumption without path heuristics.

### 3. Backfill Batches (`batches/{batch_id}.json`)
For historical backfills, batch records provide coverage mapping:
*   Includes exact mapping of `missing` timestamps as either `gap` (no source data) or `failure` (data present but decode failed).
*   Records immutable `input_identity` metadata to guarantee determinism.

## Sampling Cadence

*   **Producer SLA**: 15-minute aligned cadence.
*   **Consumer Interpolation**: If `nautilus_dev` evaluators require 5-minute sampling, the consumer MUST explicitly handle interpolation or sampling logic. The producer boundary does not implicitly support 5-minute ticks.
