# Quickstart: Reserved-Margin Validation & Portfolio-Margin Solver

## Prerequisites

- Python 3.11+ with UV
- Network access to `api.hyperliquid.xyz` (no auth required)
- Spec-026 artifacts in `data/validation/` (outlier users)

## 1. Run Margin Validation (US1)

Validate sidecar margin calculations against Hyperliquid API for outlier users:

```bash
# Validate 9 outlier users from spec-026 + control group
uv run python scripts/validate_reserved_margin.py \
  --outliers data/validation/hl_reserved_margin_outliers_eth_sample.json \
  --anchor /media/sam/4TB-NVMe/docker-volumes/hyperliquid/hl/data/periodic_abci_states/20260321/931220000.rmp \
  --output data/validation/margin_validation_report.json

# View summary
jq '{user_count, within_tolerance_count, tolerance_rate, passed}' \
  data/validation/margin_validation_report.json
```

**Expected output**: JSON report with per-user margin comparison, deviation %, and factor attribution.

## 2. Detect Portfolio-Margin Accounts (US2)

```bash
# Scan the ranked population from validation artifacts
uv run python scripts/validate_reserved_margin.py \
  --detect-modes \
  --output data/validation/portfolio_margin_accounts.json

# Scan the full reconstructed active-user population
uv run python scripts/validate_reserved_margin.py \
  --detect-modes \
  --detect-modes-full-population \
  --output data/validation/portfolio_margin_accounts_full.json
```

**Current observed result (2026-03-31)**: the corrected `userAbstraction`-based full scan classified `394/397` users successfully and found `355 cross_margin`, `36 isolated_margin`, `3 portfolio_margin`, plus abstraction counts `176 dexAbstraction`, `122 default`, `39 disabled`, `53 unifiedAccount`, `3 portfolioMargin`, `1 unknown`. Live PM validation is therefore unblocked on account discovery.

## 3. Run Solver V1.1 (US4)

After the reserved-margin formula is validated and integrated:

```bash
# Generate ETH 7d surface with V1.1
uv run python scripts/generate_liqmap.py \
  --symbol ETH --timeframe 7d --solver-version v1.1 \
  --output data/validation/liqmap_hl_eth_7d_v1.1.json

# Compare V1 vs V1.1
uv run python scripts/compare_surfaces.py \
  data/validation/liqmap_hl_eth_7d.json \
  data/validation/liqmap_hl_eth_7d_v1.1.json
```

## 4. Run Tests

```bash
# All sidecar tests (existing + new)
uv run pytest tests/test_hyperliquid_sidecar.py tests/test_margin_validator.py tests/test_api_client.py tests/test_portfolio_solver.py -v

# With coverage
uv run pytest tests/ -k "hyperliquid or margin or portfolio" --cov=src.liquidationheatmap.hyperliquid --cov-report=term-missing
```

## Success Criteria Verification

| Criterion | Command | Target |
|-----------|---------|--------|
| SC-001: Margin within 1% | `jq '.tolerance_rate' report.json` | >= 0.9 |
| SC-002: PM detection 100% | `jq '.margin_mode_distribution' report.json` | No UNKNOWN |
| SC-003: PM solver liq_px within 1% | `jq '[.results[] | select(.margin_mode=="portfolio_margin") | .positions[].liq_px_deviation_pct] | map(select(. <= 1.0)) | length' report.json` | >= 90% |
| SC-004: V1.1 vs V1 documented | `diff` surface artifacts | Explainable changes |
| SC-005: No unknown gaps > 5% | `jq '[.results[] | .factor_attribution.unknown_residual] | map(select(. > 0.05)) | length' report.json` | 0 |
