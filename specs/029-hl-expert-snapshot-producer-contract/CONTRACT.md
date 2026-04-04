# Producer Contract Lock-In (Phase 1)

This document formalizes the decisions made during Phase 1 of spec-029 (Contract Lock-In).

## 1. Canonical Policy Tags (T002)

*   `v1` = canonical
*   `v2` = `shadow/control`
*   `v3` / `v4` / `v5` = experimental

## 2. Minimum `ExpertSnapshotArtifact` Field Set (T004)

Every exported expert artifact MUST contain at least the following fields:

*   `expert_id`: string (e.g., "v1", "v2")
*   `symbol`: string (e.g., "BTCUSDT")
*   `snapshot_ts`: string (UTC RFC 3339 / ISO8601 with `Z` suffix)
*   `reference_price`: float64
*   `bucket_grid`: object (explicit `price_levels` OR `min_price`, `max_price`, `step`)
*   `long_distribution`: object (price level mappings to values as float64)
*   `short_distribution`: object (price level mappings to values as float64)
*   `research_policy_tag`: string (e.g., "canonical", "shadow/control")
*   `source_metadata`: object
*   `generation_metadata`: object

## 3. Minimum `ExpertSnapshotManifest` Field Set (T004)

Every exported batch manifest MUST contain at least:

*   `snapshot_ts` (or batch equivalent)
*   `experts`: object containing entries for ALL five expert channels (`v1`, `v2`, `v3`, `v4`, `v5`).
    *   Each entry MUST have at least:
        *   `expert_id`: string
        *   `availability_status`: string (e.g., "available", "missing", "failed_decode", "not_built")
        *   `artifact_path`: string (if available)
        *   `research_policy_tag`: string
        *   `source_metadata`: object (or failure metadata)

## 4. Canonical Timestamp Semantics (T004A)

*   `snapshot_ts` = The exported evaluation-point identity timestamp. This is the canonical time for downstream consumers.
*   `run_ts` = The actual producer execution timestamp.
*   Format: Both MUST be encoded in UTC RFC 3339 / ISO8601 format with the `Z` suffix (e.g., `2026-04-03T12:00:00Z`).

## 5. Manifest Rules (T004B)

*   ALL five expert channels (`v1`, `v2`, `v3`, `v4`, `v5`) are ALWAYS present in the manifest.
*   Missing experts MUST be represented with explicit `availability_status` rather than being silently omitted.

## 6. Producer Cadence vs Consumer Sampling (T019)

*   **Producer Cadence:** The producer contract guarantees a 15-minute generation cadence. It does NOT silently promise or attempt to operate at a 5-minute interval.
*   **Consumer Sampling:** Any future evaluator-side functionality requiring 5-minute sampling MUST handle interpolation or sampling explicitly on the consumer side. The boundary remains explicitly 15-minute aligned.
