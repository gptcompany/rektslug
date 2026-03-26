# Feature Specification: Consumer-Side ABCI Checkpoint Persistence (7d Window)

**Feature Branch**: `028-consumer-checkpoint-7d`
**Created**: 2026-03-24
**Status**: Draft
**Input**: Consumer-side ABCI checkpoint persistence for 7-day liquidation analysis window
**Dependencies**: spec-026 (sidecar, ABCI decode), spec-027 (solver V1.1 with validated margin formula)

## Context

The Hyperliquid node producer retains `periodic_abci_states` for only ~2 days on a rolling basis. Each snapshot is ~1.1GB (MessagePack), produced at ~15-minute cadence (~96/day). The sidecar (spec-026) can decode and filter these snapshots to extract target-relevant user state. However, the sidecar cannot produce accurate 7-day liquidation surfaces because the source data expires before the analysis window closes.

This spec defines a consumer-owned persistence layer that archives compact checkpoints of target-relevant account state for at least 7 days, enabling reproducible 7d risk-surface generation without depending on the producer's retention policy.

Design informed by Cosmos/Tendermint ADR-042 (State Sync) and ADR-053 (State Sync Prototype) patterns: periodic, deterministic, consistent, asynchronous, garbage-collected snapshots.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compact Checkpoint Archival (Priority: P1)

As a liquidation-map operator, I need the consumer layer to automatically archive compact checkpoints of target-relevant account state from ABCI snapshots so that I retain at least 7 days of history even after the producer rolls off old snapshots.

**Why this priority**: Without 7d retention, the sidecar can only produce risk surfaces for the current ~2d window. This is the foundational capability that everything else depends on.

**Independent Test**: Run the archival process for 24 hours. Verify that compact checkpoints are created at the expected cadence and that the total storage used matches estimates (50-100MB per checkpoint, ~2.4-4.8GB per day).

**Acceptance Scenarios**:

1. **Given** a new ABCI snapshot appears in `periodic_abci_states/`, **When** the checkpoint archiver processes it, **Then** a compact checkpoint is written containing only target-relevant users (BTC/ETH positions, ~60k accounts vs 1.4M full)
2. **Given** 7 days of operation, **When** I count archived checkpoints, **Then** there are approximately 672 checkpoints (96/day * 7 days) covering the full 7d window
3. **Given** checkpoints older than 7 days, **When** the garbage collector runs, **Then** expired checkpoints are deleted and storage is reclaimed

---

### User Story 2 - Checkpoint-Based 7d Risk Surface (Priority: P1)

As a liquidation-map developer, I need to generate a 7d risk-surface artifact from archived checkpoints so that the analysis window is not limited by the producer's 2d retention.

**Why this priority**: This is the primary consumer of US1. Without it, archiving checkpoints has no value.

**Independent Test**: After 7+ days of archival, generate an ETH 7d risk surface from checkpoints and compare against a fresh ABCI-based surface for the overlapping 2d window.

**Acceptance Scenarios**:

1. **Given** 7 days of archived checkpoints, **When** I run the risk-surface generator with `--timeframe-days 7`, **Then** it produces a valid surface artifact using checkpoint data
2. **Given** a checkpoint-based 2d surface and a live ABCI-based 2d surface for the same window, **When** compared, **Then** liquidation prices match exactly (both use the same solver)
3. **Given** an interrupted archival (1-hour gap), **When** the risk-surface generator runs, **Then** it detects the gap, reports it, and produces a best-effort surface using available checkpoints

---

### User Story 3 - Incremental Replay Between Checkpoints (Priority: P3)

As a liquidation-map developer, I need to replay fills and order events between checkpoints so that I can track how liquidation surfaces evolve over time within the 7d window, not just snapshot them at checkpoint times.

**Why this priority**: This is an enhancement over pure checkpoint-based analysis. It provides path-exactness between anchors by replaying `node_fills_by_block` + `node_order_statuses_by_block`. Deferred because checkpoint-only analysis already delivers significant value.

**Independent Test**: For two consecutive checkpoints, replay all fills/events between them and compare the resulting state against the second checkpoint. Pass if state matches within solver tolerance.

**Acceptance Scenarios**:

1. **Given** two consecutive checkpoints (T1, T2) and the fill/event stream between them, **When** I replay events starting from T1 state, **Then** the reconstructed state at T2 matches the actual T2 checkpoint for all target-relevant position fields
2. **Given** a replay window with a transfer/deposit event, **When** the replayer encounters it, **Then** the event is flagged as "unhandled path-exactness gap" in the replay log

---

### Edge Cases

- What happens when the producer skips a snapshot (15-minute gap becomes 30-minute)?
- How does the archiver handle corrupted or truncated ABCI snapshots?
- What if disk space runs out before 7 days of checkpoints are archived?
- How are new assets (not BTC/ETH) handled if they become relevant mid-window?
- What happens if the ABCI snapshot format changes between checkpoints?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST monitor the producer's `periodic_abci_states/` directory and detect new snapshots within 5 minutes of creation
- **FR-002**: System MUST extract and archive only target-relevant user state (accounts with BTC/ETH positions + cross-margin-relevant off-target exposure) from each ABCI snapshot
- **FR-003**: System MUST store compact checkpoints keyed by block number with deterministic, reproducible content
- **FR-004**: System MUST retain archived checkpoints for a configurable duration (default: 7 days)
- **FR-005**: System MUST garbage-collect expired checkpoints automatically
- **FR-006**: System MUST report storage usage metrics (total size, checkpoint count, oldest/newest block numbers)
- **FR-007**: System MUST detect and report gaps in the checkpoint sequence (missed or corrupted snapshots)
- **FR-008**: System MUST support generating risk-surface artifacts from archived checkpoints using the same solver as live ABCI analysis
- **FR-009**: System MUST handle concurrent access safely (archiver writing while risk-surface generator reads)

### Key Entities

- **CompactCheckpoint**: Filtered ABCI state for target-relevant users at a specific block number. Contains: block number, timestamp, user states (balances, positions, funding accumulators), oracle prices, margin tier metadata
- **CheckpointIndex**: Manifest of all archived checkpoints with block numbers, timestamps, file sizes, and integrity hashes
- **RetentionPolicy**: Configurable rules for checkpoint retention duration and garbage collection cadence
- **GapReport**: Record of missing or corrupted checkpoints in the archive sequence

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Compact checkpoints are at least 90% smaller than full ABCI snapshots (target: ~50-100MB vs ~1.1GB)
- **SC-002**: 7 days of checkpoints consume less than 70GB of storage
- **SC-003**: Risk surfaces generated from checkpoints are identical to live ABCI surfaces for the same time window (zero deviation on liquidation prices)
- **SC-004**: Checkpoint archival completes within 5 minutes of source snapshot availability (no backlog accumulation)
- **SC-005**: Gaps in the checkpoint sequence are detected and reported within the next archival cycle

## Scope Boundary

### In Scope
- Compact checkpoint extraction from ABCI snapshots
- 7d retention with garbage collection
- Checkpoint-based risk-surface generation
- Gap detection and reporting
- Storage metrics

### Not In Scope
- Modifying the Hyperliquid node producer (stays read-only consumer)
- Real-time streaming or WebSocket interfaces
- Cross-machine replication of checkpoints
- Reserved-margin or portfolio-margin formula (spec-027)
- Incremental replay between checkpoints is P3 / stretch goal

## Assumptions

- Producer `periodic_abci_states/` directory is accessible on the local filesystem
- The sidecar's existing ABCI decode/filter code (spec-026) can be reused for checkpoint extraction
- NVMe storage on Workstation has sufficient free space for 70GB of checkpoint data
- The ABCI snapshot format is stable for the duration of the 7d retention window
- Block numbers are monotonically increasing and unique per snapshot
