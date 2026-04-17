# Plan: Bybit Historical Producer Bridge (spec-034)

## Phase 1: Source and Layout Freeze

1. Freeze which historical Bybit input classes are required per channel
2. Freeze the normalized local layout and naming rules
3. Freeze provenance fields required for source-to-normalized traceability

## Phase 2: Normalization Layer

1. Implement raw historical readers for 3TB-WDC downloader outputs
2. Normalize trades, orderbook, klines, funding, and OI into producer-readable files
3. Persist normalization metadata and versioning

## Phase 3: Producer Integration

1. Extend Bybit readiness logic to recognize normalized historical inputs
2. Extend the Bybit producer to read normalized historical inputs
3. Preserve `spec-030` manifest/artifact semantics

## Phase 4: Coverage and Determinism Validation

1. Validate sample historical windows for `bybit_standard`
2. Validate sample historical windows for `depth_weighted`
3. Confirm deterministic reruns from identical normalized inputs

## Phase 5: Handoff

1. Document historical coverage, gaps, and unresolved windows
2. Produce sample manifests for historical-only windows
3. Update roadmap/scope references
