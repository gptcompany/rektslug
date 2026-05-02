# Quickstart: Scorecard Runtime Evidence Plane

## Generate Evidence

```bash
uv run python scripts/generate-scorecard-evidence.py \
  --snapshot-root data/validation/expert_snapshots/hyperliquid \
  --output-root data/validation/scorecards \
  --symbols BTCUSDT ETHUSDT \
  --experts v1 v3 v4 v5 \
  --adaptive
```

Expected outputs:

```text
data/validation/scorecards/latest.json
data/validation/scorecards/latest-summary.json
data/validation/scorecards/runs/{run_id}/scorecard.json
data/validation/scorecards/runs/{run_id}/summary.json
data/validation/scorecards/runs/{run_id}/inputs.json
```

## Query Endpoint

```bash
curl -fsS http://127.0.0.1:8002/ops/scorecard/latest | jq .
```

## Query Compact Summary

```bash
curl -fsS http://127.0.0.1:8002/ops/summary | jq '.details.scorecard_status, .details.scorecard_summary'
```

## Validation

```bash
uv run pytest -q \
  tests/test_scorecard/test_runtime_evidence.py \
  tests/integration/test_ops_scorecard_endpoint.py
```

## Boundary

This evidence can be displayed by `nautilus_dev`, but it does not change:

- operator pause state
- risk reduce-only state
- entries enabled state
- live/paper readiness gate ownership
