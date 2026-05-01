# Liquidation Confirmation Event Contract

This directory freezes the retained liquidation-confirmation source contract for
`spec-041`.

Contract:
- persisted files under this directory are the scorecard confirmation source
- file format target: JSONL
- one row per liquidation event
- normalized event shape must match `src.exchanges.base.NormalizedLiquidation`
  semantically, including at least:
  - `symbol`
  - `price`
  - `side`
  - `timestamp`

Notes:
- this directory is the retained source boundary for scorecard confirmation
- `spec-041` must not rely on an implicit or ad hoc WebSocket archive
- later slices may add concrete readers/writers against this directory
