# Tasks: Provider Liq-Map Comparison

**Input**: `specs/017-liqmap-provider-comparison/spec.md`
**Dependencies**: `spec-016` local liq-map route/runtime gates should already be usable
**Feature Type**: Validation/comparison workflow using existing provider tooling

## Format: `[ID] [P?] [Story?] Description`
- **[P]**: Can run in parallel
- **[US#]**: User Story mapping
- Include exact file paths in descriptions

## User Stories

| Story | Priority | Description |
|-------|----------|-------------|
| **US1** | P0 | Freeze a strict liq-map-only comparison matrix for BTC/ETH and 1d/1w |
| **US2** | P0 | Capture CoinAnk liq-map artifacts reliably, preferring native download when available |
| **US3** | P0 | Capture Coinglass liqMap artifacts reliably, preferring authenticated REST replay |
| **US4** | P1 | Normalize and compare local/CoinAnk/Coinglass runs into auditable reports |

---

## Phase 1: Setup & Scope Lock

**Purpose**: Lock the workflow to the intended product, symbols, and timeframes.

- [X] T001 Confirm the active reference matrix in `docs/runbooks/chart-routes.md` remains BTC/ETH x 1d/1w only
- [X] T002 Verify local runtime gates before provider comparison: `rektslug-api`, `rektslug-sync`, DuckDB catch-up, and `/liquidations/levels`
- [X] T003 [P] Verify local Playwright/Chromium prerequisites for screenshot tooling
- [X] T004 [P] Verify required `dotenvx` secrets for `COINANK_*` / `COINGLASS_*` are available to the existing scripts

**Checkpoint**: The comparison workflow has a fixed matrix and valid runtime prerequisites.

---

## Phase 2: Foundational Workflow Constraints

**Purpose**: Ensure the orchestration and manifests cannot drift into heatmap or unsupported timeframe work.

- [X] T005 Restrict or preset `scripts/run_provider_api_comparison.py` to `liq-map` semantics for this spec
- [X] T006 Add or confirm explicit `1d` / `1w` preset handling in `scripts/run_provider_api_comparison.py`
- [X] T007 [P] Add or confirm manifest fields for `product=liq-map`, `symbol`, `timeframe`, `provider_url`, and `capture_mode`
- [X] T008 [P] Add or confirm artifact naming that cleanly separates `BTC/ETH` and `1d/1w` runs under `data/validation/`

**Checkpoint**: The orchestration layer can no longer silently mix heatmap or unsupported timeframe artifacts into this workstream.

---

## Phase 3: User Story 1 - Matrix Definition (Priority: P0) 🎯 MVP

**Goal**: Every comparison run targets exactly one supported `(symbol, timeframe)` pair.

**Independent Test**: A run request outside `BTC/ETH x 1d/1w` fails fast with a clear error.

### Tests / Guards

- [X] T009 [P] [US1] Add CLI/contract test coverage for unsupported timeframes or symbols in the comparison runner
- [X] T010 [P] [US1] Add manifest validation coverage ensuring `liq-map` is the only accepted product in this spec workflow

### Implementation

- [X] T011 [US1] Encode the supported comparison matrix in `scripts/run_provider_api_comparison.py`
- [X] T012 [US1] Thread the matrix metadata into output manifests and summaries

**Checkpoint**: A valid run is always one of the 4 supported matrix entries.

---

## Phase 4: User Story 2 - CoinAnk Capture (Priority: P0)

**Goal**: Capture CoinAnk liq-map artifacts reliably for the supported matrix.

**Independent Test**: A BTC 1W run produces CoinAnk raw payloads plus a screenshot artifact and records the exact CoinAnk URL.

### Tests / Guards

- [X] T013 [P] [US2] Add or confirm test coverage for CoinAnk URL generation in `scripts/coinank_screenshot.py`
- [X] T014 [P] [US2] Add or confirm manifest coverage for CoinAnk capture metadata in `scripts/capture_provider_api.py`

### Implementation

- [X] T015 [US2] Prefer the native CoinAnk camera/download flow when credentials and page state allow it
- [X] T016 [US2] Keep `scripts/coinank_screenshot.py` as fallback screenshot path for `1d` / `1w`
- [X] T017 [US2] Ensure CoinAnk raw payload capture remains tied to `liq-map`, not `liq-heat-map`

**Checkpoint**: CoinAnk artifacts are stable enough for repeated baseline runs.

---

## Phase 5: User Story 3 - Coinglass Capture (Priority: P0)

**Goal**: Capture Coinglass liqMap artifacts reliably for `1d` and `1w`.

**Independent Test**: A BTC 1W run produces a Coinglass `liqMap` artifact with explicit timeframe metadata and no heatmap substitution.

### Tests / Guards

- [X] T018 [P] [US3] Add or confirm coverage for the `1d -> interval=1, limit=1500` mapping
- [X] T019 [P] [US3] Add or confirm coverage for the `1w -> interval=5, limit=2000` mapping
- [X] T020 [P] [US3] Add or confirm manifest coverage for `capture_mode`, `timeframe_applied`, and provider URL

### Implementation

- [X] T021 [US3] Default Coinglass capture to authenticated REST replay when available
- [X] T022 [US3] Keep browser route interception as fallback when REST replay fails
- [X] T023 [US3] Ensure only documented `liqMap` endpoints are accepted for this spec workflow

**Checkpoint**: Coinglass artifacts are explicit, replayable, and cleanly separated from heatmap products.

---

## Phase 6: User Story 4 - Comparison & Reporting (Priority: P1)

**Goal**: Generate auditable normalized reports for local/CoinAnk/Coinglass liq maps.

**Independent Test**: One run yields a manifest plus a normalized report with provider-specific bucket deltas and capture references.

### Tests / Guards

- [X] T024 [P] [US4] Add or confirm coverage for normalized manifest/report loading in `scripts/compare_provider_liquidations.py`
- [X] T025 [P] [US4] Add or confirm coverage for provider gap analysis on liq-map-only manifests in `scripts/provider_gap_analysis.py`

### Implementation

- [X] T026 [US4] Emit normalized comparison output for local, CoinAnk, and Coinglass in `scripts/compare_provider_liquidations.py`
- [X] T027 [US4] Emit scenario-level residual-gap output for the same run in `scripts/provider_gap_analysis.py`
- [X] T028 [US4] Persist summaries to validation DuckDB when the workflow is run in persisted mode

**Checkpoint**: A single run can be audited later without reopening provider pages.

---

## Phase 7: Baseline Matrix Runs

**Purpose**: Produce the first stable baseline across the supported matrix.

- [X] T029 [P] Run baseline comparison for BTC 1D
- [X] T030 [P] Run baseline comparison for BTC 1W
- [X] T031 [P] Run baseline comparison for ETH 1D
- [X] T032 [P] Run baseline comparison for ETH 1W
- [X] T033 [P] Review artifacts and reject any run that accidentally used heatmap endpoints or unsupported timeframes

**Checkpoint**: The repo has a clean first baseline for all 4 supported matrix entries.

**Completion Notes**:

- Baseline BTC 1D:
  - `data/validation/raw_provider_api/20260310T173131Z/manifest.json`
  - `data/validation/provider_comparisons/20260310T173211Z_provider_liquidations.json`
  - `data/validation/provider_comparisons/20260310T173211Z_provider_gap_analysis.json`
- Baseline BTC 1W:
  - `data/validation/raw_provider_api/20260310T173221Z/manifest.json`
  - `data/validation/provider_comparisons/20260310T173302Z_provider_liquidations.json`
  - `data/validation/provider_comparisons/20260310T173302Z_provider_gap_analysis.json`
- Baseline ETH 1D:
  - `data/validation/raw_provider_api/20260310T173310Z/manifest.json`
  - `data/validation/provider_comparisons/20260310T173350Z_provider_liquidations.json`
  - `data/validation/provider_comparisons/20260310T173351Z_provider_gap_analysis.json`
- Baseline ETH 1W:
  - `data/validation/raw_provider_api/20260310T173509Z/manifest.json`
  - `data/validation/provider_comparisons/20260310T173550Z_provider_liquidations.json`
  - `data/validation/provider_comparisons/20260310T173550Z_provider_gap_analysis.json`
- All 4 regenerated baselines normalize exactly `coinank`, `coinglass`, and `rektslug`.
- Under `matrix-preset spec-017`, the workflow now excludes `bitcoincounterflow` and rejects non-`liq-map` product drift.

---

## Phase 8: Polish & Documentation

**Purpose**: Make the workflow easy to repeat without re-discovery.

- [X] T034 Update `docs/provider-api-comparison.md` with the narrowed `spec-017` liq-map-only scope if needed
- [X] T035 [P] Update `docs/runbooks/chart-routes.md` or an adjacent runbook with the exact comparison commands for BTC/ETH 1d/1w
- [X] T036 [P] Add a short artifact checklist for validating that a run is truly `liq-map` and not `heatmap`

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup & Scope Lock
  └─→ Phase 2: Foundational Workflow Constraints
        └─→ Phase 3: US1 Matrix Definition
              ├─→ Phase 4: US2 CoinAnk Capture ──┐
              └─→ Phase 5: US3 Coinglass Capture ─┤
                                                   └─→ Phase 6: US4 Comparison & Reporting
                                                         └─→ Phase 7: Baseline Matrix Runs
                                                               └─→ Phase 8: Polish & Documentation
```

### User Story Dependencies

- **US1**: depends on Phase 1 and 2 only
- **US2**: depends on US1
- **US3**: depends on US1
- **US4**: depends on US2 and US3 artifacts being available

### Parallel Opportunities

- `T003` and `T004`
- `T007` and `T008`
- `T009` and `T010`
- `T013` and `T014`
- `T018`, `T019`, and `T020`
- `T024` and `T025`
- `T029`, `T030`, `T031`, and `T032`
- `T033`, `T035`, and `T036`

## MVP Strategy

1. Lock the matrix to `BTC/ETH x 1d/1w`
2. Make one clean BTC 1W run end-to-end
3. Verify CoinAnk and Coinglass artifacts are both true `liq-map` captures
4. Expand to the remaining 3 matrix entries

## Notes

- `spec-016` remains the prerequisite visual baseline for the local CoinAnk-style liq-map route.
- `spec-017` is a provider comparison workflow, not a new chart implementation spec.
- If provider routes drift, update the scripts/docs, not the scope.
