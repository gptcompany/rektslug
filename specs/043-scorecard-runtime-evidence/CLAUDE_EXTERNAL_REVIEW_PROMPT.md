# External Review Prompt: spec-043 Scorecard Runtime Evidence Plane

You are reviewing `rektslug` branch `043-scorecard-runtime-evidence`.

## Scope

Review only spec-043 scorecard runtime evidence work. Do not review unrelated dirty
workspace files unless they directly affect this feature.

Primary commits:

- `9a7a930 docs(scorecard): define runtime evidence spec`
- `2883511 docs(scorecard): apply speckit.analyze remediation across all artifacts`
- `f841f05 docs(scorecard): runtime evidence documentation (Phase 10)`
- `b6ed6da fix(scorecard): harden runtime evidence plane`

Key files:

- `src/liquidationheatmap/scorecard/runtime.py`
- `src/liquidationheatmap/scorecard/calibration.py`
- `scripts/generate-scorecard-evidence.py`
- `src/liquidationheatmap/api/routers/ops.py`
- `tests/test_scorecard/test_runtime_evidence.py`
- `tests/integration/test_ops_scorecard_endpoint.py`
- `tests/test_scorecard/test_calibration.py`
- `tests/test_scorecard/test_deploy_guardrails.py`
- `specs/043-scorecard-runtime-evidence/*`

## Expected Behavior

The feature promotes spec-041/spec-042 scorecard output into retained runtime
evidence:

- Generate `latest.json` and `latest-summary.json` from retained expert snapshots.
- Require a real retained price-path JSON via `--price-path`.
- Validate `ExpertScorecardBundle` before healthy endpoint status.
- Expose `GET /ops/scorecard/latest`.
- Add compact `scorecard_status` and `scorecard_summary` to `GET /ops/summary`.
- Fail closed on missing/invalid artifacts.
- Preserve read-only boundary: no execution/risk/operator mutation.
- Respect repo `CLAUDE.md`: Adaptive Signals, Fixed Safety; four pillars
  `Probabilistico`, `Non Lineare`, `Non Parametrico`, `Scalare`.

## Verification Already Run

```bash
uv run pytest -q tests/test_scorecard tests/integration/test_ops_scorecard_endpoint.py
# 84 passed, 4 warnings

uv run ruff check \
  src/liquidationheatmap/scorecard/runtime.py \
  src/liquidationheatmap/scorecard/calibration.py \
  src/liquidationheatmap/api/routers/ops.py \
  scripts/generate-scorecard-evidence.py \
  tests/test_scorecard/test_runtime_evidence.py \
  tests/test_scorecard/test_calibration.py \
  tests/test_scorecard/test_deploy_guardrails.py \
  tests/integration/test_ops_scorecard_endpoint.py
# All checks passed

uv run ruff format --check \
  src/liquidationheatmap/scorecard/runtime.py \
  src/liquidationheatmap/scorecard/calibration.py \
  src/liquidationheatmap/api/routers/ops.py \
  scripts/generate-scorecard-evidence.py \
  tests/test_scorecard/test_runtime_evidence.py \
  tests/test_scorecard/test_calibration.py \
  tests/test_scorecard/test_deploy_guardrails.py \
  tests/integration/test_ops_scorecard_endpoint.py
# 8 files already formatted
```

Smoke CLI:

```bash
uv run python scripts/generate-scorecard-evidence.py \
  --snapshot-root data/validation/expert_snapshots/hyperliquid \
  --price-path /tmp/generated-price-path.json \
  --output-dir /tmp/scorecard-out \
  --symbols BTCUSDT \
  --experts v1 \
  --limit-manifests 1 \
  --enable-adaptive
# generated latest.json and latest-summary.json
```

## Review Goals

Find bugs, contract drift, false-green tests, safety boundary violations, or
production-readiness gaps. Prioritize findings over summaries.

Specifically check:

1. `scripts/generate-scorecard-evidence.py`
   - Does it require and load real price-path JSON correctly?
   - Does it fail closed on missing snapshot manifests, missing price path, invalid
     JSON, invalid bundle, or blocking issues?
   - Does it avoid fabricated experts/symbols/observation counts?
   - Is `--enable-adaptive` / `--disable-adaptive` behavior coherent?

2. `src/liquidationheatmap/scorecard/runtime.py`
   - Is deterministic JSON actually reproducible?
   - Are atomic writes safe enough?
   - Is quality classification correct for stale, coverage gaps, missing price path,
     missing volume, missing liquidation events, and no slices?
   - Does `scorecard_status_from_details()` aggregate all quality dimensions?

3. `src/liquidationheatmap/api/routers/ops.py`
   - Does `/ops/scorecard/latest` return the provider envelope consistently for
     healthy, degraded, blocked, and unavailable states?
   - Does `/ops/summary` include only compact scorecard data and not full bundle or
     calibration internals?
   - Does missing scorecard evidence degrade provider summary correctly without
     claiming execution ownership?

4. Tests
   - Are previous false-green cases actually covered now?
   - Are there missing tests for degraded endpoint status, invalid summary schema,
     stale artifact behavior, and CLI real-path execution?

5. Four pillars and safety
   - Are signal/evidence parameters adaptive or labeled as method/governance
     constants?
   - Are safety/governance constants kept explicit and not made adaptive?
   - Does the feature remain read-only and separate from `nautilus_dev` execution?

## Known Non-Scope Dirty Files

The workspace may show unrelated dirty files from previous work, including
`docs/EXCHANGE_*`, multiple `scripts/*`, `src/exchanges/hyperliquid.py`,
`src/liquidationheatmap/streams/liquidations.py`, and old exchange tests. Ignore
them unless the current branch changes require them.

## Desired Output

Return findings ordered by severity with file/line references. If no blocking
findings remain, say so explicitly and list residual risks or recommended
follow-up tests.
