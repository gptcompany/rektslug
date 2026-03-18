# Spec 023: ETH Production Validation

## Overview

Complete the ETH/USDT production validation gap. The BTC/USDT public liq-map route
has been visually validated against CoinAnK (spec-016, 017, 022), but ETH/USDT has
only been data-validated — never visually confirmed end-to-end on the public route.

This spec closes the multi-asset validation gap by running the same visual and
structural checks on ETH that BTC already passed.

## Scope

### In Scope

- Visual validation of ETH/USDT 1d and 1w on the public liq-map route
- Structural comparison of ETH public builder output vs CoinAnK reference
- ETH-specific grid step and range envelope verification
- ETH leverage ladder distribution check (bucket counts, tier spread)
- Update provider comparison baselines for ETH (spec-017 workflow)

### Out of Scope

- New ETH-specific calculation logic (reuses spec-022 public builder)
- BTC re-validation (already passed)
- Symbols beyond ETH/USDT
- liq-heat-map validation (separate spec)

## Dependencies

- spec-022 public liqmap builder (completed)
- spec-017 provider comparison workflow (completed)
- Running API instance with fresh ETH data

## Functional Requirements

- **FR-001**: ETH/USDT 1d public route MUST render with distinct grid step vs BTC 1d.
- **FR-002**: ETH/USDT 1w public route MUST render with wider range than 1d.
- **FR-003**: ETH bucket counts MUST be non-trivial (>= 15 long + 15 short buckets).
- **FR-004**: ETH cumulative curves MUST be monotonic and reach the grid boundary.
- **FR-005**: Provider comparison baselines for ETH 1d/1w MUST be regenerated and archived.

## Success Criteria

- **SC-001**: ETH 1d and 1w screenshots pass manual visual review against CoinAnK reference.
- **SC-002**: ETH structural metrics (bucket count, range span, cumulative shape) are within 20% of BTC equivalents.
- **SC-003**: No regression on BTC routes after ETH validation runs.
