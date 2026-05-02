# Data Model: Scorecard Runtime Evidence Plane

## ScorecardEvidenceEnvelope

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `provider_id` | `str` | yes | Must be `rektslug` |
| `schema_version` | `str` | yes | Endpoint schema version |
| `generated_at` | `datetime` | yes | Response generation timestamp |
| `status` | `str` | yes | `HEALTHY`, `DEGRADED`, `BLOCKED`, `UNAVAILABLE` |
| `freshness_sla_secs` | `int` | yes | Governance constant |
| `last_error` | `str | null` | yes | Last validation/read error |
| `details` | `ScorecardEvidenceDetails` | yes | Evidence payload |

## ScorecardEvidenceDetails

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `artifact_path` | `str` | yes | Canonical latest artifact path |
| `summary_path` | `str` | yes | Compact summary path |
| `artifact_generated_at` | `datetime` | yes | Artifact timestamp |
| `artifact_age_secs` | `int` | yes | Current age |
| `adaptive_mode` | `bool` | yes | Whether spec-042 adaptive mode was used |
| `experts` | `list[str]` | yes | Expert IDs represented |
| `symbols` | `list[str]` | yes | Symbols represented |
| `slice_count` | `int` | yes | Scorecard slice count |
| `observation_count` | `int` | yes | Total sample count |
| `dominance_row_count` | `int` | yes | Expert comparison rows |
| `coverage_gap_count` | `int` | yes | Data coverage gaps |
| `blocking_issues` | `list[str]` | yes | Hard issues |
| `quality` | `ScorecardQualitySummary` | yes | Data-quality summary |
| `calibration_metadata` | `dict` | yes | Derived/method/governance values |
| `artifact_links` | `dict[str, str]` | yes | Retained paths |

## ScorecardQualitySummary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `snapshot_coverage_status` | `str` | yes | `HEALTHY`, `DEGRADED`, `BLOCKED`, `UNAVAILABLE` |
| `price_path_coverage_status` | `str` | yes | Price path availability/continuity |
| `volume_coverage_status` | `str` | yes | Volume-clock usability |
| `liquidation_confirmation_status` | `str` | yes | Confirmation event availability |
| `schema_validation_status` | `str` | yes | Bundle validation result |
| `reproducibility_hash` | `str` | yes | Stable hash of canonical JSON |

## Error Envelope

When `status` is `UNAVAILABLE` or `BLOCKED`, `details` is a reduced object:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `blocking_issues` | `list[str]` | yes | Issues preventing healthy status |

All other `ScorecardEvidenceDetails` fields are omitted. Implementation SHOULD use
a union type or optional fields to represent both healthy and error payloads.

## CalibrationMetadataEntry

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `kind` | `str` | yes | `derived`, `method_constant`, `governance_constant` |
| `name` | `str` | yes | Parameter/method name |
| `value` | `Any` | yes | Selected value or value map |
| `method` | `str` | yes | How it was selected |
| `input_count` | `int | null` | no | Number of observations/ticks used |
| `reason` | `str` | yes | Why it is acceptable |

### Serialization Note

The `calibration_metadata` field in the artifact and contract is a
`dict[str, CalibrationMetadataEntry]` keyed by parameter name. The `name` field
in each entry matches its dict key. Additional domain-specific fields (e.g.,
`n_bootstrap`, `seed_policy`, `selected_values`) are stored inside `value` and
are not part of the base schema. See `contracts/ops-scorecard-latest.md` for
concrete examples.

## Retained Files

`latest.json` contains:

- full validated `ExpertScorecardBundle`
- evidence metadata
- quality summary
- calibration metadata
- provenance

`latest-summary.json` contains:

- endpoint-ready compact details
- status
- blocking issues
- artifact links

The summary MUST be enough for `/ops/summary`; the full artifact belongs to
`/ops/scorecard/latest`.
