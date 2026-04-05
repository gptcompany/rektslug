# Feature Specification: Hyperliquid Expert Snapshot Producer Contract

**Feature Branch**: `029-hl-expert-snapshot-producer-contract`
**Created**: 2026-04-03
**Status**: Draft
**Input**: Producer-side contract for Hyperliquid expert snapshots consumed by the liquidation-map evaluator in `nautilus_dev` (`spec-061`)
**Dependencies**: spec-026 (Hyperliquid model calibration), spec-028 (consumer checkpoint discipline), `nautilus_dev/spec-061` (consumer/evaluator)

## Context

`rektslug` is the producer of the five Hyperliquid liquidation-map variants:

- `v1` - truthful/internal full-universe baseline
- `v2` - CoinGlass replay/control (`shadow` only)
- `v3` - internal top-positions branch
- `v4` - internal position-first branch
- `v5` - internal risk-first branch

Recent work closed one important question:

- `v1` remains the canonical internal map
- `v2` remains a `shadow` control
- `v5` is not promoted as a new default

The next research step is no longer payload-only comparison inside `rektslug`. The next step is ex-post evaluation in `nautilus_dev` using replay and event labels (`spec-061`).

To make that possible, `rektslug` needs a stable producer contract:

- a strict snapshot schema
- deterministic export layout
- explicit producer-side scheduling semantics
- backfill rules for historical research
- a clear boundary between producer (`rektslug`) and consumer/evaluator (`nautilus_dev`)

This spec defines that producer contract. It does **not** define the evaluator itself.

## Scope

### In Scope

- Define the canonical producer schema for `v1`..`v5` expert snapshots
- Define export layout and manifest rules for consumer pickup
- Define producer-side run identity and scheduling semantics
- Define historical backfill requirements for expert snapshots
- Define explicit producer/consumer boundary with `nautilus_dev`

### Out of Scope

- Ex-post labels, metrics, or expert weighting
- Replay/event-engine logic
- Redis/message-bus publication
- Promotion of any expert over `v1`
- Turning `v2` into a live production dependency

## Producer / Consumer Boundary

### `rektslug` Responsibilities

- Build expert snapshots for `v1`..`v5`
- Normalize each snapshot into a declared contract
- Persist timestamp-addressable artifacts and manifests
- Mark research/control status such as `v2` shadow semantics
- Provide deterministic metadata for replay/backfill consumers

### `nautilus_dev` Responsibilities

- Consume expert snapshots as external inputs
- Attach snapshots to replayed event timelines
- Build ex-post labels and metrics
- Maintain expert ranking and soft weights
- Publish finalized feature bundles

### Explicit Rule

`rektslug` is the `producer of expert state`.
`nautilus_dev` is the `consumer and evaluator of expert state`.

Neither repo should silently absorb the other role during MVP.

## User Scenarios & Testing

### User Story 1 - Stable Expert Snapshot Export (Priority: P1)

As a consumer of Hyperliquid expert maps, I need every snapshot to use a stable, explicit schema so that downstream replay and evaluation do not depend on ad hoc script-specific formats.

**Why this priority**: Without a stable producer contract, `spec-061` will inherit avoidable ambiguity and fragile glue code.

**Independent Test**: Generate one snapshot batch containing `v1`..`v5`, validate the schema, and confirm that a consumer can resolve all experts for one timestamp from the manifest without reading repo-specific implementation details.

**Acceptance Scenarios**:

1. **Given** a producer run for one symbol and timestamp, **When** export completes, **Then** every available expert snapshot conforms to the same schema and carries its `expert_id`.
2. **Given** a consumer reading the export manifest, **When** it resolves one timestamp, **Then** it can locate all available expert artifacts and their metadata without hard-coded path guesses.
3. **Given** `v2` is present, **When** its metadata is inspected, **Then** it is explicitly marked as `shadow/control`.

---

### User Story 2 - Deterministic Producer Scheduling Semantics (Priority: P1)

As a system integrator, I need producer-side run timing and identity to be deterministic so that replay-side consumers can align snapshots with event history reliably.

**Why this priority**: The evaluator can only be trusted if snapshot timing is reproducible and explainable.

**Independent Test**: Simulate baseline and extra runs, then verify that producer metadata records the actual run timestamp, run reason, prior run reference, and next-baseline semantics consistently.

**Acceptance Scenarios**:

1. **Given** a baseline producer run, **When** the artifact is written, **Then** metadata records `run_reason=baseline` and the run timestamp used for scheduling.
2. **Given** an extra producer run occurs before the next baseline, **When** metadata is inspected, **Then** it records the extra-run reason and updates `last_actual_run_ts`.
3. **Given** two runs are very close in time, **When** the consumer reads them, **Then** ordering and uniqueness are still unambiguous.

---

### User Story 3 - Historical Backfill For Research (Priority: P1)

As a quantitative researcher, I need historical expert snapshots produced on a coherent timeline so that replay-driven evaluation can score the experts across local historical data.

**Why this priority**: The evaluator has little value without research-grade historical inputs.

**Independent Test**: Run a backfill across a bounded interval and verify that outputs are gap-reportable, manifest-indexed, and aligned to a declared timeline policy.

**Acceptance Scenarios**:

1. **Given** a historical interval and a backfill command, **When** export completes, **Then** manifests expose timestamp coverage, missing experts, and input provenance.
2. **Given** an expert cannot be produced for one timestamp, **When** the batch manifest is written, **Then** the gap is explicit rather than silently omitted.
3. **Given** the same backfill is rerun with the same inputs, **When** artifacts are compared, **Then** content and manifests are deterministic apart from declared generation metadata.

## Edge Cases

- **Missing experts for a timestamp**: The manifest MUST list the missing expert with `availability_status: "not_built"`. Silent omission is never acceptable (FR-021, FR-022).
- **`v2` capture data stale, undecodable, or unavailable**: The manifest MUST list `v2` with `availability_status: "failed_decode"` and include failure metadata describing the decode or staleness reason.
- **Bucket-grid mismatch between experts**: Every exported artifact MUST be normalized onto the declared common grid. If normalization is impossible for an expert, that expert MUST be reported as `availability_status: "failed_decode"` with a note explaining the grid incompatibility.
- **Two producer runs in a short interval mapping to the same wall-clock bucket**: `run_id` and `run_ts` guarantee uniqueness of producer runs. `snapshot_ts` maintains the declared evaluation-point granularity. Two distinct runs always produce distinct `run_id` values even when `snapshot_ts` would otherwise coincide.
- **Partial backfills — gaps vs hard failures**: The batch record MUST distinguish `gap` (no source data exists for that timestamp) from `failure` (source data exists but could not be processed). Both MUST be machine-readable.
- **Source cache files from incompatible logic versions**: `source_metadata.producer_version` allows the consumer to filter or flag artifacts from older logic. The artifact is exported but flagged, not silently discarded.

## Requirements

### Functional Requirements

- **FR-001**: The producer MUST define five named expert channels: `v1`, `v2`, `v3`, `v4`, `v5`.
- **FR-002**: Every exported snapshot MUST carry `expert_id`, `symbol`, `snapshot_ts`, and `reference_price`.
- **FR-003**: Every exported snapshot MUST include both `long` and `short` bucket distributions on a declared common grid.
- **FR-004**: The producer MUST reject or explicitly flag any snapshot where the bucket grid is missing, malformed, or inconsistent with the declared contract.
- **FR-005**: The producer MUST include source metadata as defined in the Initial Contract Shape section: source path or capture root, source timestamp when available, builder/logic family, and at least one immutable input identity reference per FR-025.
- **FR-006**: The producer MUST include generation metadata sufficient to distinguish build version, run reason, and run timestamp.
- **FR-007**: `v1` MUST remain marked as the canonical internal baseline in metadata and documentation.
- **FR-008**: `v2` MUST be explicitly marked as `shadow/control` in metadata and MUST NOT be exported as a canonical or live-driving expert.
- **FR-009**: The producer MUST emit a manifest or index that maps one evaluation timestamp to the available expert snapshots and their paths.
- **FR-010**: The manifest MUST expose missing experts explicitly rather than silently omitting them.
- **FR-011**: The producer MUST record deterministic run identity fields, including at least `run_id`, `run_reason`, `run_ts`, and `last_actual_run_ts`.
- **FR-012**: The producer MUST support baseline scheduling semantics measured from `last_actual_run_ts`, not only from wall-clock slots.
- **FR-013**: If an extra run occurs before the next baseline slot, the producer MUST record metadata allowing the consumer to reconstruct that the next baseline is anchored from the extra run.
- **FR-014**: The producer MUST support historical backfill over a bounded interval with explicit coverage metadata.
- **FR-015**: The producer MUST report per-batch gaps, missing experts, and decode/source failures in a machine-readable way.
- **FR-016**: The producer MUST produce outputs that can be consumed without importing `rektslug` internal script logic into `nautilus_dev`.
- **FR-017**: The producer MAY reuse existing sidecar outputs and raw-provider captures, but the export contract MUST be stable even if internal generation paths change. Note: the existing `data/cache/hl_sidecar_*.json` files remain unchanged and continue to serve the current operational path. The export contract produces additional artifacts under `data/validation/expert_snapshots/`. The two paths coexist during MVP.
- **FR-018**: The producer MUST document the boundary with `spec-061` so that evaluator-side logic does not drift into `rektslug`.
- **FR-019**: `snapshot_ts` MUST be the canonical identity timestamp for one exported evaluation point. It MUST be encoded in UTC RFC 3339 / ISO8601 form with `Z` suffix in artifact content, manifest content, and timestamp-derived filenames.
- **FR-020**: `run_ts` MUST represent the actual producer execution timestamp and MUST remain distinct from `snapshot_ts` when the export is generated retroactively or as part of backfill.
- **FR-021**: Every manifest MUST contain entries for all five expert channels (`v1`..`v5`) even when an expert is unavailable. Missing experts MUST be represented explicitly by status rather than by omission.
- **FR-022**: Every expert entry in the manifest MUST carry an explicit availability state, with MVP-supported values at least `available`, `missing`, `failed_decode`, and `not_built`.
- **FR-023**: The common bucket grid MUST be expressed explicitly and machine-readably. MVP artifacts MUST encode either a full ordered price-level array or an equivalent canonical representation containing `min_price`, `max_price`, and `step`, plus enough information to reconstruct the exact ordered grid without inference.
- **FR-024**: The manifest MUST declare whether artifact distributions are already normalized onto the export grid or whether rebucketing would be required. MVP target is fully normalized export with no downstream rebucketing required.
- **FR-025**: Backfill determinism MUST be auditable from metadata. Exported manifests and batch records MUST include stable input identity fields such as source capture ids, source manifest ids, content digests, or equivalent immutable references sufficient to prove which inputs were used.
- **FR-026**: The producer MUST declare its own cadence semantics independently from evaluator sampling semantics. MVP producer cadence remains the currently supported producer cadence unless and until a separate producer-side change promotes denser generation.
- **FR-027**: The producer contract MUST NOT imply that `nautilus_dev` 5-minute evaluator sampling is already matched by a 5-minute `rektslug` producer cadence. Any mismatch MUST be explicit in the contract and manifests.

### Non-Functional Requirements

- **NFR-001**: Numeric precision — `reference_price`, `bucket_grid` price levels, and `long_distribution`/`short_distribution` values MUST use at least IEEE 754 float64 precision in exported JSON. Decimal128 is not required because this contract covers snapshot export, not live margin calculations.
- **NFR-002**: Export performance — a single snapshot batch export (one symbol, five experts) SHOULD complete in < 10 seconds. A one-week historical backfill SHOULD complete in < 10 minutes.
- **NFR-003**: Storage footprint — manifests and artifacts are JSON. Estimated size < 500 KB per snapshot batch (one symbol, five experts). Backfill batches scale linearly.

### Key Entities

- **ExpertSnapshotArtifact**: One expert output for one symbol and timestamp, containing expert identity, reference price, common bucket grid, long/short distributions, and provenance.
- **ExpertSnapshotManifest**: Index describing all five expert channels for one evaluation timestamp or one batch window, including availability status, missing experts, failures, and file paths.
- **ProducerRunRecord**: Metadata describing one actual producer run, including run identity, run reason, timestamps, source inputs, and declared baseline anchor.
- **BackfillBatchRecord**: Coverage summary for a historical export batch, including interval, timeline policy, missing timestamps, and generation provenance.
- **ResearchPolicyTag**: Explicit classification tag such as `canonical`, `experimental`, or `shadow/control`.
- **InputIdentityRecord**: Stable identity block for proving deterministic reruns, including immutable source ids, content digests, or source-manifest references.

## Initial Contract Shape

Each `ExpertSnapshotArtifact` MUST contain at least:

- `expert_id`
- `symbol`
- `snapshot_ts`
- `reference_price`
- `bucket_grid`
- `long_distribution`
- `short_distribution`
- `research_policy_tag`
- `source_metadata`
- `generation_metadata`

Suggested `generation_metadata` fields:

- `run_id`
- `run_reason`
- `run_ts`
- `last_actual_run_ts`
- `producer_version`
- `input_window`
- `producer_cadence`

Suggested `source_metadata` fields:

- source file or capture path
- source capture timestamp if applicable
- logic family or builder name
- decode/build notes when relevant
- immutable source identity reference(s)

### Timestamp Semantics

The contract distinguishes:

- `snapshot_ts`: canonical identity timestamp of the exported evaluation point
- `run_ts`: actual producer execution timestamp

Rules:

- `snapshot_ts` MUST be UTC RFC 3339 / ISO8601 with `Z` suffix
- manifest filenames and artifact directory names MUST be derived from
  `snapshot_ts`, not from ad hoc wall-clock formatting
- `run_ts` MUST also be stored in UTC RFC 3339 / ISO8601 with `Z` suffix
- `snapshot_ts` and `run_ts` MAY differ during backfill or retroactive export
- downstream consumers should align on `snapshot_ts`; `run_ts` exists for
  provenance, ordering, and scheduling reconstruction

### Manifest Channel Semantics

Every manifest MUST list all five expert channels:

- `v1`
- `v2`
- `v3`
- `v4`
- `v5`

For each expert, the manifest MUST include at least:

- `expert_id`
- `availability_status`
- `artifact_path` when available
- `research_policy_tag`
- `source_metadata` or failure metadata

Allowed MVP interpretation:

- the contract covers all five channels
- an expert may be unavailable at a specific timestamp
- unavailability must be explicit and machine-readable

So the absence of `v3` or another variant at one timestamp is a valid manifest
state only when it is represented as a declared unavailable channel rather than
being silently omitted.

### Common Bucket Grid Semantics

The export grid is common across experts within one `snapshot_ts`.

MVP rule:

- the producer normalizes all exported expert distributions onto one declared
  common grid before export
- the consumer should not be forced to infer or reconstruct the grid by
  comparing variant internals

The artifact MUST therefore expose one of these canonical forms:

- explicit ordered `price_levels`
- or `min_price` + `max_price` + `step` together with a declared rule that
  reconstructs the exact ordered `price_levels`

The manifest or artifact MUST also state whether:

- distributions are already normalized onto that grid
- or export failed because normalization could not be completed

MVP target is fully normalized export only.

### Input Identity And Determinism Semantics

To make backfill determinism auditable, the producer contract must record
stable source identity, not only human-readable provenance.

Acceptable identity fields include:

- source manifest id
- source capture id
- content digest or checksum
- immutable retained snapshot id

Two reruns may only be considered the same deterministic backfill when these
identity references match.

## Initial Export Layout

The producer contract SHOULD support a layout shaped like:

```text
data/validation/expert_snapshots/hyperliquid/
  manifests/
    {symbol}/
      {timestamp}.json
  artifacts/
    {symbol}/
      {timestamp}/
        v1.json
        v2.json
        v3.json
        v4.json
        v5.json
  batches/
    {batch_id}.json
```

Equivalent layouts are acceptable if they preserve:

- stable path derivation
- one manifest-to-many-artifacts resolution
- explicit batch/backfill coverage reporting

Timestamp-derived paths MUST be based on canonical `snapshot_ts`.

## Initial Scheduling Semantics

The producer side does **not** need to own the full evaluator trigger engine. It does need to expose deterministic semantics for actual runs.

The contract MUST support these minimum producer-side concepts:

- `baseline` run
- `extra` run
- `manual` run
- `backfill` run

For any actual run, metadata MUST allow the consumer to reconstruct:

- why the run happened
- when it actually happened
- which prior actual run it follows
- whether it re-anchors the baseline schedule

### Producer Cadence vs Consumer Sampling

Current producer reality:

- `scripts/precompute_hl_sidecar.py` is currently designed around a `15m`
  periodic producer cadence

Consumer-side research reality:

- `spec-061` in `nautilus_dev` may evaluate on a denser `5m` schedule or on a
  replay-driven subset of timestamps

The producer contract must not blur these two layers together.

MVP rule:

- `rektslug` exports the producer cadence it actually supports
- manifests and generation metadata must declare that cadence explicitly
- `nautilus_dev` remains responsible for any denser evaluator-side sampling,
  interpolation policy, or subset selection

This avoids silently promising a `5m` producer timeline before producer-side
generation actually supports it.

## Initial Backfill Semantics

Historical backfill MUST declare:

- target interval
- timeline policy
- symbol set
- expert set
- success/failure per timestamp
- missing or undecodable inputs

The first acceptable timeline policy is:

- fixed cadence timeline aligned to the producer's declared baseline cadence

Later timeline policies may add:

- extra-run inclusion where historical trigger provenance exists
- mixed baseline-plus-extra timelines

## Success Criteria

### Measurable Outcomes

- **SC-001**: A consumer can resolve all available experts for one timestamp using only the manifest contract, without repo-specific path heuristics.
- **SC-002**: `v2` is always explicitly labeled `shadow/control` in exported metadata.
- **SC-003**: Re-running the same bounded backfill with the same inputs yields deterministic manifests and artifact contents apart from declared generation timestamps or version metadata.
- **SC-004**: Missing experts and decode/source failures are explicit in machine-readable manifests rather than discoverable only by missing files.
- **SC-005**: `nautilus_dev` can consume exports without importing `rektslug` script internals.

## Boundary Discipline

### In Scope For `rektslug`

- producing expert artifacts
- declaring research policy tags
- exporting manifests and batch coverage
- documenting producer-side scheduling semantics
- historical backfill materialization

### Not In Scope For `rektslug`

- event-driven replay evaluation
- order-book-aware labeling
- expert ranking or soft weighting
- Redis publication for the hot path
- execution-facing feature governance

## Existing Touchpoints

Current implementation touchpoints likely to feed this contract:

- `scripts/precompute_hl_sidecar.py`
- `scripts/compare_hl_sidecar_variants.py`
- `docs/runbooks/hyperliquid-liqmap-checkpoint.md`

These are informative inputs, not the contract itself. The contract defined here should remain stable even if those scripts evolve.

## Detailed Design Clarifications From Working Session

This section promotes the working-session findings into explicit producer-side rules so the contract is not left to interpretation.

### Clarification 1 - The Producer Scope Is All Five Experts

The producer contract must cover:

- `v1`
- `v2`
- `v3`
- `v4`
- `v5`

Even though recent comparison work focused on `v1`, `v2`, and `v5`, the producer side must not narrow the export contract to only those three.

Interpretation rule:

- `v1` is canonical
- `v2` is `shadow/control`
- `v3`, `v4`, `v5` remain experimental branches

### Clarification 2 - `v2` Must Be Exported Explicitly As Shadow

The producer must not leave `v2` policy to consumer inference.

`v2` metadata must state that it is:

- replay-derived
- control/shadow only
- not a canonical or live-driving export

This is especially important because `v2` may still be highly valuable in research outputs and divergence analysis.

### Clarification 3 - The Producer Contract Must Not Leak Internal Script Logic

The consumer in `nautilus_dev` should not need to know:

- which script produced a snapshot
- which cache file naming convention happened to exist that day
- how `v2` was reconstructed internally
- which builder variant was called directly

The producer may change its internal implementation, but the exported snapshot contract and manifest contract must remain stable.

### Clarification 4 - Export Must Be Manifest-First, Not Path-Guessing

The consumer should be able to resolve one evaluation timestamp by reading a manifest, not by guessing file paths such as:

- `data/cache/hl_sidecar_btcusdt.json`
- `data/cache/hl_sidecar_v5_btcusdt.json`
- ad hoc batch-specific filenames

Therefore the producer contract must be organized around:

- a manifest per timestamp or batch
- explicit artifact paths
- explicit missing-expert entries

The absence of a file should never be the only way to discover a gap.

### Clarification 4A - Five Channels Always Exist At Manifest Level

The working resolution to the `v3` ambiguity is:

- the contract always covers five expert channels
- a channel may be unavailable at a specific timestamp
- manifest entries must still exist for all five channels

This preserves a stable consumer contract without pretending that every expert
is always buildable at every timestamp during MVP.

### Clarification 5 - Snapshot Metadata Must Be Strong Enough For Replay Alignment

The working session concluded that the producer side does not own the evaluator, but it does own deterministic timing metadata.

At minimum, exported metadata must let a consumer answer:

- when was this snapshot actually produced?
- why was it produced?
- what was the previous actual run?
- is this run baseline, extra, manual, or backfill?
- does this run re-anchor the baseline cadence?

This is why `run_id`, `run_reason`, `run_ts`, and `last_actual_run_ts` are not optional convenience fields.

### Clarification 6 - Producer Scheduling Semantics Must Match The Agreed Baseline Rule

The scheduler/evaluator conversation established a precise rule:

- baseline cadence is measured from `last_actual_run_ts`
- if an extra run occurs, the next baseline is measured from that extra run

The producer does not have to implement the full adaptive engine in this spec, but its metadata must preserve that rule so the consumer can reconstruct it.

### Clarification 7 - Historical Backfill Must Be Research-Grade, Not Best-Effort Opaque

Backfill is not an afterthought. It is required for the evaluator to score the experts across local historical data.

That means a backfill batch must expose:

- target interval
- timeline policy
- symbol set
- expert set
- coverage
- missing timestamps
- missing experts
- source/decode failures

If a backfill is partial, the manifest must say so explicitly. Silent omission is not acceptable.

### Clarification 8 - Determinism Matters More Than Convenience

If the same backfill is run twice with the same inputs, outputs should be deterministic apart from explicitly declared generation metadata such as:

- producer version
- generation timestamp

This matters because the evaluator should be able to compare results across runs without artifact drift caused by loosely defined producer behavior.

That determinism claim is valid only when the input identity block matches.
Human-readable provenance alone is insufficient.

### Clarification 9 - Common Bucket Grid Must Be An Explicit Contract Field

The consumer/evaluator expects normalized expert distributions on a common evaluation grid.

Therefore the producer contract must make the bucket grid explicit and machine-readable, not implicit in:

- `bin_size` alone
- display-only metadata
- assumptions inferred from a file name or builder family

If an expert cannot conform to the declared grid policy, the artifact must be rejected or explicitly flagged.

The agreed interpretation for MVP is:

- common within one exported `snapshot_ts`
- explicitly machine-readable
- already normalized before consumer pickup

### Clarification 10 - Source Provenance Must Be Sufficient For Audit And Diagnostics

The working session repeatedly relied on source provenance to reason about whether an artifact was trustworthy. The contract should therefore preserve:

- source path or capture root
- source timestamp or anchor when available
- builder or logic family
- notes about reconstruction mode when relevant

This is especially important for:

- `v2`, where replay origin matters
- experimental branches where builder semantics may evolve

### Clarification 11 - `rektslug` Owns Producer Semantics, Not Consumer Evaluation

This boundary needs to remain explicit:

- `rektslug` produces expert state
- `nautilus_dev` evaluates expert state

`rektslug` should not absorb:

- replay/event-engine logic
- ex-post labels
- weighting/ranking logic
- Redis/event-bus distribution as an MVP dependency

The producer side exists to make the consumer/evaluator possible, not to duplicate it.

### Clarification 12 - Existing Scripts Are Inputs, Not The Contract

The current implementation touchpoints matter because they already contain useful logic and assumptions:

- `scripts/precompute_hl_sidecar.py`
- `scripts/compare_hl_sidecar_variants.py`
- `docs/runbooks/hyperliquid-liqmap-checkpoint.md`

But the export contract must outlive the exact behavior of those files. If the scripts change, the consumer contract should not break.

### Clarification 13 - Producer 15m Cadence Does Not Equal Consumer 5m Sampling

The working session identified a real cadence mismatch risk:

- current producer path is `15m`
- desired evaluator sampling may be `5m`

The contract-level resolution is:

- make the producer cadence explicit
- do not silently imply `5m` producer support
- let the consumer layer own denser replay-side sampling policy

## Reference Producer Map

This map makes the producer-side integration targets explicit.

### Current Builder / Cache Touchpoints

Primary generation path:

- [precompute_hl_sidecar.py](/media/sam/1TB/rektslug/scripts/precompute_hl_sidecar.py)
  - designed to run every `15` minutes via cron
  - writes atomic JSON files to `data/cache/`
  - contains the current internal builder logic for Hyperliquid sidecar outputs

Variant comparison / validation path:

- [compare_hl_sidecar_variants.py](/media/sam/1TB/rektslug/scripts/compare_hl_sidecar_variants.py)
  - already resolves `v1`, `v2`, and `v5` for raw-USD comparisons
  - already reconstructs `v2` from local CoinGlass replay when no explicit `--cache-v2` is provided
  - provides a current touchpoint for extracting distribution-level export logic

Runbook / decision log:

- [hyperliquid-liqmap-checkpoint.md](/media/sam/1TB/rektslug/docs/runbooks/hyperliquid-liqmap-checkpoint.md)
  - records the verdict that `v1` stays canonical
  - records that `v2` stays shadow/control
  - records that `v5` remains experimental

### Current Producer Behaviors That Need Formalization

Already observable in current code or workflow:

- atomic cache writes
- symbol-scoped sidecar artifacts
- variant-specific outputs
- local replay-based reconstruction for `v2`
- comparison/reporting logic around variant payloads

Still needing explicit contract formalization:

- manifest structure
- batch coverage record
- machine-readable missing-expert reporting
- stable artifact directory for consumer pickup
- explicit producer run metadata
- stable backfill layout

## MVP Non-Ambiguity Summary

For avoidance of doubt, the producer contract defined by this spec means:

- export all five experts, not just the current comparison subset
- list all five expert channels in every manifest, even when some are unavailable
- keep `v1` marked canonical
- keep `v2` explicitly marked `shadow/control`
- treat `snapshot_ts` as the canonical exported time identity
- keep `run_ts` distinct as producer execution provenance
- export machine-readable bucket grids and side-aware distributions
- normalize exported distributions onto the declared common grid before consumer pickup
- emit manifest-driven artifact resolution, not path-guessing
- preserve deterministic run identity metadata
- preserve auditable input identity for deterministic backfill claims
- preserve enough metadata to reconstruct baseline-vs-extra run semantics
- report missing experts and source/decode failures explicitly
- support research-grade historical backfill with coverage metadata
- keep producer cadence explicit and do not silently promise `5m` producer support
- keep internal script logic behind a stable producer contract
- leave labels, scoring, weighting, and replay orchestration to `nautilus_dev`
