# Contract: GET /ops/scorecard/latest

## Success: Healthy

```json
{
  "provider_id": "rektslug",
  "schema_version": "1.0.0",
  "generated_at": "2026-05-02T16:00:00Z",
  "status": "HEALTHY",
  "freshness_sla_secs": 86400,
  "last_error": null,
  "details": {
    "artifact_path": "/app/data/validation/scorecards/latest.json",
    "summary_path": "/app/data/validation/scorecards/latest-summary.json",
    "artifact_generated_at": "2026-05-02T15:55:00Z",
    "artifact_age_secs": 300,
    "adaptive_mode": true,
    "experts": ["v1", "v3", "v4", "v5"],
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "slice_count": 120,
    "observation_count": 4800,
    "dominance_row_count": 360,
    "coverage_gap_count": 0,
    "blocking_issues": [],
    "quality": {
      "snapshot_coverage_status": "HEALTHY",
      "price_path_coverage_status": "HEALTHY",
      "volume_coverage_status": "HEALTHY",
      "liquidation_confirmation_status": "HEALTHY",
      "schema_validation_status": "HEALTHY",
      "reproducibility_hash": "sha256:..."
    },
    "calibration_metadata": {
      "bootstrap": {
        "kind": "method_constant",
        "name": "bootstrap",
        "value": {"n_bootstrap": 1000, "seed_policy": "sha256(slice_key)[:4]"},
        "method": "fixed_default",
        "input_count": null,
        "reason": "Standard bootstrap iteration count; computational budget allows 1000"
      }
    },
    "artifact_links": {
      "scorecard": "/app/data/validation/scorecards/latest.json",
      "summary": "/app/data/validation/scorecards/latest-summary.json"
    }
  }
}
```

## Missing Artifact

HTTP `503`

```json
{
  "provider_id": "rektslug",
  "schema_version": "1.0.0",
  "generated_at": "2026-05-02T16:00:00Z",
  "status": "UNAVAILABLE",
  "freshness_sla_secs": 86400,
  "last_error": "scorecard artifact missing",
  "details": {
    "blocking_issues": ["scorecard artifact missing"]
  }
}
```

## Summary Integration

`GET /ops/summary` MUST include:

```json
{
  "details": {
    "scorecard_status": "HEALTHY",
    "scorecard_summary": {
      "artifact_generated_at": "2026-05-02T15:55:00Z",
      "adaptive_mode": true,
      "experts": ["v1", "v3", "v4", "v5"],
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "observation_count": 4800,
      "slice_count": 120,
      "coverage_gap_count": 0
    }
  }
}
```
