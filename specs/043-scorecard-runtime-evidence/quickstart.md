# Scorecard Runtime Evidence Quickstart

Generate the scorecard evidence artifacts:
```bash
uv run scripts/generate-scorecard-evidence.py \
  --snapshot-root data/validation/expert_snapshots/hyperliquid \
  --price-path data/validation/scorecard_price_path.json \
  --output-dir data/validation/scorecards
```

Check the status via API:
```bash
curl http://localhost:8002/ops/scorecard/latest
curl http://localhost:8002/ops/summary
```
