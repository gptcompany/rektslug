# Feature Specification: Bybit Historical Producer Bridge

**Feature Branch**: `034-bybit-historical-producer-bridge`
**Created**: 2026-04-17
**Status**: Implemented
**Input**: Close the `spec-030` follow-up so historical Bybit windows on 3TB-WDC
become producer-readable inside `rektslug`
**Dependencies**: spec-030 (modeled snapshot contract), spec-031 (public serving),
ccxt-data-pipeline live catalog, bybit_data_downloader historical dataset

## Context

`rektslug` already knows that Bybit source data exists in two places:

- live producer-readable Parquet under `ccxt-data-pipeline`
- historical downloader output under `3TB-WDC`

The remaining gap is not source existence. The remaining gap is that the
historical downloader outputs are still not normalized into a producer-readable
format that the Bybit modeled-snapshot producer can consume directly.

Today that means:

- live Bybit windows can be `available`
- historical-only windows on 3TB-WDC remain `blocked_source_unverified`
- downstream consumers still cannot rely on deterministic historical Bybit
  replay coverage from `rektslug` alone

## Goal

Make historical Bybit windows on 3TB-WDC first-class producer inputs for
`rektslug`, with deterministic normalization, explicit provenance, and manifested
artifact output under the existing modeled-snapshot contract.

## Scope

### In Scope

- define a normalized producer-readable layout for historical Bybit source files
- implement readers/normalizers for 3TB-WDC Bybit historical inputs
- bridge normalized historical inputs into the existing Bybit producer path
- preserve deterministic provenance and input identity
- resolve historical readiness status from `blocked_source_unverified` to either
  `available`, `partial`, or `blocked_source_missing` based on real normalized coverage

### Out of Scope

- new public route behavior
- real-time exchange streaming adapters
- new Bybit execution strategy logic
- changing the modeled snapshot schema introduced by `spec-030`

## Problem Statement

The repo currently distinguishes between:

1. source files that exist
2. source files the producer can actually read deterministically

For historical Bybit windows, only the first condition is true. That creates a
false ceiling:

- the data exists
- the readiness gate can see it
- but the producer still cannot use it

This spec closes that gap.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST define a normalized historical input layout for
  Bybit trades, orderbook, klines, funding, and open interest where applicable.
- **FR-002**: The normalizer MUST preserve source identity from the original
  3TB-WDC files into producer-readable metadata.
- **FR-003**: The Bybit producer MUST be able to resolve a historical requested
  window to normalized local inputs without importing logic from external repos.
- **FR-004**: The readiness gate MUST distinguish between:
  - raw historical source exists but not normalized
  - normalized historical source available
  - historical source missing
- **FR-005**: The output contract for manifests and artifacts MUST remain the
  `spec-030` modeled snapshot contract.
- **FR-006**: Historical normalization MUST be deterministic for the same source
  files and normalization version.
- **FR-007**: The bridge MUST explicitly document uncovered windows and any
  partial channel degradation.

### Non-Functional Requirements

- **NFR-001**: Historical normalization SHOULD be append-safe and resumable.
- **NFR-002**: The bridge SHOULD not require the downstream producer to parse raw
  csv.gz, zip, or custom downloader layouts directly.
- **NFR-003**: The normalizer SHOULD support audit-friendly retention of source
  path, date, and digest metadata.

## Success Criteria

- **SC-001**: A historical Bybit window covered only by 3TB-WDC data can produce
  a manifest with producer-readable provenance and no `blocked_source_unverified`
  status.
- **SC-002**: The readiness gate reports historical normalized availability
  accurately for both `bybit_standard` and `depth_weighted`.
- **SC-003**: A consumer can replay a historical Bybit artifact from manifest
  metadata without depending on external repo logic.
