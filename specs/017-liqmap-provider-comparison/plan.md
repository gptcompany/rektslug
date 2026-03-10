# Implementation Plan: Provider Liq-Map Comparison

**Spec**: `specs/017-liqmap-provider-comparison/spec.md`
**Feature Type**: Validation/comparison workflow (not new implementation)
**Branch**: master (no feature branch — tooling-only spec)

## Technical Context

### Existing Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| `scripts/run_provider_api_comparison.py` | Exists | Full orchestrator: capture + compare + persist |
| `scripts/capture_provider_api.py` | Exists | CoinAnk/Coinglass/BCF raw capture with Playwright |
| `scripts/compare_provider_liquidations.py` | Exists | Normalization + pairwise comparison |
| `scripts/provider_gap_analysis.py` | Exists | Scenario analysis + DuckDB persistence |
| `scripts/coinank_screenshot.py` | Exists | `--product map` for liq-map screenshots |
| `scripts/validate_liqmap_visual.py` | Exists | Visual validation with freshness gates |
| `data/validation/raw_provider_api/` | 52+ runs | Timestamped capture directories |
| `data/validation/provider_comparisons/` | 27+ reports | Normalized comparison JSONs |
| `data/validation/validation_results.duckdb` | Exists | Validation tracking DB |
| `docs/provider-api-comparison.md` | Exists | Full workflow documentation |
| `docs/runbooks/chart-routes.md` | Exists | Reference matrix BTC/ETH x 1d/1w |

### Technology Choices

| Choice | Justification |
|--------|---------------|
| Playwright | Already used for all provider captures; CoinAnk login + Coinglass route interception |
| DuckDB | Already hosts validation tables; no new storage system needed |
| dotenvx | Already manages `COINANK_*` and `COINGLASS_*` secrets |
| pytest | Standard test runner; existing fixtures in `tests/conftest.py` |

### Required Environment Variables

Exact variable names already used by the existing scripts:

- `COINANK_USER`
- `COINANK_PASSWORD`
- `COINGLASS_USER_LOGIN`
- `COINGLASS_USER_PASSWORD`

Optional but useful for local Coinglass decoder/bundle workflows:

- `COINGLASS_APP_BUNDLE`

### Reference URLs

Primary local / CoinAnk liq-map matrix:

- Local BTC 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- Local BTC 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local ETH 1D: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- Local ETH 1W: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- CoinAnk BTC 1D: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d`
- CoinAnk BTC 1W: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- CoinAnk ETH 1D: `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1d`
- CoinAnk ETH 1W: `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1w`

Documented Coinglass liq-map references used by the existing tooling:

- Page target: `https://www.coinglass.com/pro/futures/LiquidationMap`
- API target: `https://capi.coinglass.com/api/index/5/liqMap`

### What Already Works

- CoinAnk capture with login + native download fallback (`--product map`)
- Coinglass capture via REST replay (`--coinglass-mode rest`) and browser fallback
- Manifest generation with provider URLs, capture mode, timeframe metadata
- Pairwise normalization with `dataset_kind` field distinguishing liq-map from heatmap
- Scenario-based gap analysis with DuckDB persistence
- 6 timeframe mappings verified for Coinglass (1d, 1w, 1m, 3m, 6m, 1y)

### What Needs Work

1. **Scope enforcement**: No hard guard preventing heatmap endpoints from leaking into a liq-map-only run
2. **Matrix lock**: `run_provider_api_comparison.py` accepts any `--coin` and `--timeframe` — no preset matrix for spec-017
3. **Test coverage**: Zero unit tests for capture, manifest validation, or orchestration scripts
4. **Artifact naming**: Timestamped directories exist but don't encode `product=liq-map` explicitly
5. **Baseline runs**: No frozen baseline for the 4 matrix entries (BTC/ETH x 1d/1w)

## Constitution Check

| Principle | Applicable? | Status | Action |
|-----------|-------------|--------|--------|
| Mathematical Correctness (MUST) | Low | N/A | Comparison workflow, not calculation |
| Test-Driven Development (MUST) | Yes | Gap | Tests must precede scope-enforcement implementation |
| Exchange Compatibility (MUST) | Low | N/A | Provider comparison, not exchange calculation |
| Performance Efficiency (SHOULD) | Yes | Specified | NFR-001..NFR-004 define budgets |
| Data Integrity (MUST) | Yes | Covered | FR-011 + FR-012 cover audit trail |
| Graceful Degradation (SHOULD) | Yes | Specified | EC-001..EC-005 cover failure modes |
| Progressive Enhancement (SHOULD) | Yes | OK | Phased delivery in tasks.md |
| Documentation Completeness (MUST) | Yes | Phase 8 | Docs update planned |

**Gate result**: PASS — no constitution violations. TDD gap addressed by tasks.md test-first ordering.

## Research Findings

### R1: Scope Enforcement Strategy

**Decision**: Add a `--product` filter to `run_provider_api_comparison.py` (default: `liq-map`) that propagates to capture and comparison phases.

**Rationale**: The capture script already captures all endpoints indiscriminately. Rather than filtering at capture time (which would lose data), filter at comparison/reporting time by `dataset_kind`. The manifest already records enough metadata to distinguish liq-map from heatmap artifacts.

**Alternatives considered**:
- Filter at capture time (rejected: loses potentially useful data for future specs)
- Separate script (rejected: YAGNI — existing orchestrator handles it with one flag)

### R2: Matrix Lock Strategy

**Decision**: Add a `--matrix-preset` option (default: `spec-017`) that constrains `--coin` and `--timeframe` to `{BTC,ETH} x {1d,1w}`. Unsupported combinations fail fast with a clear error.

**Rationale**: The orchestrator already accepts `--coin` and `--timeframe`. A preset is a thin validation layer, not a new abstraction.

**Alternatives considered**:
- Config file with matrix definitions (rejected: YAGNI for 4 entries)
- Separate CLI wrapper (rejected: unnecessary indirection)

### R3: CoinAnk Capture Mode

**Decision**: Use existing `coinank_screenshot.py --product map` for screenshots. Use `capture_provider_api.py` with CoinAnk login for raw payload capture. The `getLiqMap` parser is preferred over `getAggLiqMap`.

**Rationale**: Both paths are already implemented and documented. `getLiqMap` exposes symbol-level leverage ladders (x25 through x100), which is more granular than the aggregate endpoint.

### R4: Coinglass Capture Mode

**Decision**: Default to `--coinglass-mode rest` (authenticated REST replay). Browser route interception is the fallback. Target endpoint: `capi.coinglass.com/api/index/5/liqMap`.

**Rationale**: REST replay produces identical payloads to browser capture (verified 2026-03-03), is faster, and doesn't require Playwright for Coinglass. The TOTP+AES mechanism is already implemented.

**Risk**: Coinglass bundle updates may invalidate TOTP secret / AES key. Monitoring via `coinglass_bundle_report.py` is already in place.

### R5: Test Strategy

**Decision**: Unit tests with mocked provider payloads extracted from existing manifests in `data/validation/raw_provider_api/`. No live API calls in tests.

**Rationale**: 52+ real capture runs provide ample fixture data. Live API tests would be flaky and slow.

**Fixture sources**:
- CoinAnk: Extract a `getLiqMap` response from an existing BTC 1W manifest
- Coinglass: Extract a `liqMap` response from an existing BTC 1W manifest
- Manifest schema: Use any existing `manifest.json` as golden reference

## Architecture

### Data Flow (spec-017 narrowed)

```
run_provider_api_comparison.py
  --product liq-map --matrix-preset spec-017
  │
  ├─ capture_provider_api.py
  │   ├─ CoinAnk: getLiqMap (browser + login)
  │   └─ Coinglass: liqMap (REST replay, browser fallback)
  │   → data/validation/raw_provider_api/{timestamp}Z/manifest.json
  │
  ├─ coinank_screenshot.py --product map
  │   → data/validation/raw_provider_api/{timestamp}Z/coinank_screenshot.png
  │
  ├─ compare_provider_liquidations.py
  │   → data/validation/provider_comparisons/{timestamp}_provider_liquidations.json
  │   (filtered to dataset_kind=liqmap only)
  │
  └─ provider_gap_analysis.py
      → data/validation/provider_comparisons/{timestamp}_provider_gap_analysis.json
      → DuckDB: provider_gap_analysis_* tables (if --persist-db)
```

### Artifact Directory Structure

```
data/validation/
├── raw_provider_api/
│   └── {YYYYMMDDTHHMMSS}Z/
│       ├── manifest.json           # product, symbol, timeframe, provider URLs
│       ├── coinank/
│       │   ├── 01_getLiqMap.json
│       │   └── summary.json
│       ├── coinglass/
│       │   ├── 01_liqmap.json
│       │   └── summary.json
│       └── coinank_screenshot.png  # optional
├── provider_comparisons/
│   ├── {timestamp}_provider_liquidations.json
│   └── {timestamp}_provider_gap_analysis.json
└── validation_results.duckdb       # longitudinal tracking
```

### Key Interfaces

**Orchestrator CLI** (existing, to be extended):
```bash
dotenvx run -f /media/sam/1TB/.env -- uv run python scripts/run_provider_api_comparison.py \
  --provider both \
  --coin BTC \
  --timeframe 1w \
  --exchange binance \
  --coinglass-mode rest \
  --coinglass-url "https://www.coinglass.com/pro/futures/LiquidationMap"
```

**New flags** (spec-017 additions):
- `--product liq-map` — filter comparison output to `dataset_kind=liqmap`
- `--matrix-preset spec-017` — constrain coin/timeframe to BTC/ETH x 1d/1w

**Manifest fields** (already present, to be validated):
- `product`: `liq-map` (new, explicit)
- `providers[].capture_mode`: `browser` | `rest`
- `providers[].timeframe_applied`: `true` | `false`
- `args.coin`, `args.timeframe`, `args.exchange`

## Data Model

No new database tables. Existing DuckDB tables are sufficient:

| Table | Purpose | Already Exists? |
|-------|---------|-----------------|
| `provider_comparison_runs` | Run metadata | Yes |
| `provider_comparison_datasets` | Normalized datasets per provider | Yes |
| `provider_comparison_pairs` | Pairwise comparison metrics | Yes |
| `provider_gap_analysis_runs` | Gap analysis run metadata | Yes |
| `provider_gap_analysis_scenarios` | Scenario-level metrics | Yes |
| `provider_gap_analysis_leverage` | Leverage composition snapshots | Yes |

**New field** in `provider_comparison_runs`: `product TEXT DEFAULT 'liq-map'` — added via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

## Phases (aligned with tasks.md)

| Phase | Purpose | Tasks | Parallel? |
|-------|---------|-------|-----------|
| 1 | Setup & Scope Lock | T001-T004 | T003, T004 parallel |
| 2 | Foundational Workflow Constraints | T005-T008 | T007, T008 parallel |
| 3 | Matrix Definition (MVP) | T009-T012 | T009, T010 parallel |
| 4 | CoinAnk Capture | T013-T017 | T013, T014 parallel |
| 5 | Coinglass Capture | T018-T023 | T018-T020 parallel |
| 6 | Comparison & Reporting | T024-T028 | T024, T025 parallel; depends on Phase 4+5 |
| 7 | Baseline Matrix Runs | T029-T033 | T029-T032 parallel |
| 8 | Polish & Documentation | T034-T036 | T035, T036 parallel |

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Coinglass bundle update breaks TOTP/AES | Capture fails | `coinglass_bundle_report.py` monitors hash; REST fallback to browser |
| CoinAnk login flow changes | Screenshot capture fails | `coinank_screenshot.py` has crop fallback; payload capture via public endpoint |
| Provider rate-limiting during baseline runs | Incomplete baselines | EC-002 specifies retry+backoff; sequential runs per provider |
| DuckDB lock contention during persist | 503 from API | Validation DuckDB is separate from main DB; no contention expected |

## Quickstart

### Prerequisites

```bash
# Verify runtime services
curl -sf http://localhost:8002/health | jq .

# Verify secrets
dotenvx run -f /media/sam/1TB/.env -- env | grep -E 'COINANK_USER|COINANK_PASSWORD|COINGLASS_USER_LOGIN|COINGLASS_USER_PASSWORD|COINGLASS_APP_BUNDLE'

# Verify Playwright
uv run playwright install chromium 2>/dev/null || echo "Already installed"
```

### Single Matrix Entry Run (BTC 1W)

```bash
dotenvx run -f /media/sam/1TB/.env -- uv run python scripts/run_provider_api_comparison.py \
  --provider both \
  --coin BTC \
  --timeframe 1w \
  --exchange binance \
  --coinglass-mode rest \
  --coinglass-url "https://www.coinglass.com/pro/futures/LiquidationMap"
```

### Full Matrix Run

```bash
for coin in BTC ETH; do
  for tf in 1d 1w; do
    dotenvx run -f /media/sam/1TB/.env -- uv run python scripts/run_provider_api_comparison.py \
      --provider both \
      --coin "$coin" \
      --timeframe "$tf" \
      --exchange binance \
      --coinglass-mode rest \
      --coinglass-url "https://www.coinglass.com/pro/futures/LiquidationMap"
    sleep 10  # Avoid rate-limiting
  done
done
```

### Review Results

```bash
# Latest comparison report
ls -t data/validation/provider_comparisons/*_provider_liquidations.json | head -1 | xargs cat | jq '.summary'

# DuckDB longitudinal query
uv run python scripts/provider_comparison_sql_report.py --json | jq '.latest_runs'
```
