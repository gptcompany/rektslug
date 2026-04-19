# Tasks: spec-037 Nautilus Liquidation Bridge Operational Closeout

## Phase 1: Spec And Contract Freeze

- [x] T001 Freeze multi-repo ownership boundaries for `rektslug` and `nautilus_dev`
- [x] T002 Freeze promotion gates `G0` through `G4`
- [x] T003 Freeze required JSON schemas for smoke, soak, continuous, and recovery evidence
- [x] T004 Freeze fail-closed conditions and account-flatness requirements

## Phase 2: Long Soak

- [x] T005 Define review-grade soak profiles:
  - short: `2` cycles for development smoke
  - standard: `20` cycles for pre-review
  - extended: `50` cycles or time-bounded equivalent for release evidence
- [x] T005a Verify guarded smoke command refuses to place orders without explicit
  `--confirm-testnet-order` flag; run once without flag and assert exit code
  is non-zero and zero venue orders are created
- [x] T006 Add or verify aggregate metrics in the soak report:
  `passed_cycles`, `failed_cycles`, `feedback_rows`, `open_positions`,
  `open_orders`, `cleanup_count`, `total_pnl`, per-cycle latency
- [x] T007 Run standard soak on Hyperliquid testnet and retain aggregate JSON
- [x] T008 Run extended soak or document why standard soak is the accepted gate
- [x] T009 Update runbook with accepted soak profile, command, and evidence path

## Phase 3: Real-Signal Continuous Paper/Testnet Mode

- [x] T010 Define continuous-mode runtime config:
  symbol allowlist, minimum confidence, max size, max accepted signals,
  max runtime window, and dry-run/testnet execution mode
- [x] T011 Implement or wire dry-run real-signal consumer that records decisions
  without venue orders
- [x] T012 Implement or wire testnet real-signal consumer with conservative
  execution controls
- [x] T013 Persist lifecycle state for every observed signal:
  `received`, `rejected`, `accepted`, `order_submitted`, `order_rejected`,
  `filled`, `position_opened`, `position_closed`, `feedback_published`,
  `feedback_persisted`
- [x] T013a Write failing tests for lifecycle state tracker before implementation
  (TDD RED): assert state transitions match FR-005 states, reject invalid
  transitions, persist to expected store
- [x] T014 Run continuous dry-run over a bounded real-signal window and retain report
- [x] T015 Run continuous testnet/paper over a bounded real-signal window and retain report

## Phase 4: Recovery And Fault Injection

- [x] T016 Define supported fault-injection points:
  pre-submit, post-submit/pre-fill, open-position/pre-close,
  post-close/pre-feedback, Redis unavailable, DuckDB unavailable
- [ ] T016a Write failing tests for fault-injection hooks before implementation
  (TDD RED): assert each hook triggers the expected failure mode, assert recovery
  leaves account flat
- [ ] T017 Add deterministic test hooks or controlled script flags for each fault point
- [ ] T018 [P] Verify restart recovery for post-submit/pre-fill
- [ ] T019 [P] Verify restart recovery for open-position/pre-close
- [ ] T020 [P] Verify restart recovery for post-close/pre-feedback
- [ ] T021 [P] Verify Redis unavailable path fails closed and preserves retryable feedback where applicable
- [ ] T022 [P] Verify DuckDB unavailable path fails closed and does not report success
- [ ] T023 Verify final account state is flat and has zero open orders after every recovery test

## Phase 5: Metrics And Review Evidence

- [ ] T024 Produce lifecycle metrics summary:
  per each FR-005 lifecycle state: `received`, `rejected`, `accepted`,
  `order_submitted`, `order_rejected`, `filled`, `position_opened`,
  `position_closed`, `feedback_published`, `feedback_persisted`; plus cleanup
  metric: `residual_orders_cleaned`
- [ ] T025 Produce latency summary:
  signal-to-submit, submit-to-fill, open-to-close, close-to-feedback,
  feedback-to-persist
- [ ] T025a Tag every failure in evidence artifacts as `source: venue` or
  `source: bridge`; verify at least one example of each category is present in
  recovery reports
- [ ] T026 Produce final `EVIDENCE_PACKAGE.md`
- [ ] T027 Produce machine-readable `evidence_summary.json`
- [ ] T028 Update `docs/EXECUTION_READINESS_ROADMAP.md` with spec-037 result
- [ ] T029 Update `docs/EXECUTION_READINESS_EXTERNAL_REVIEW.md` with review entry points
- [ ] T030 Final review: confirm no secrets in logs, docs, JSON, or committed artifacts
- [ ] T031 Mark spec status implemented only after `G0` through `G4` are satisfied
