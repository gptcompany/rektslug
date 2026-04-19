# Tasks: spec-037 Nautilus Liquidation Bridge Operational Closeout

## Phase 1: Spec And Contract Freeze

- [ ] T001 Freeze multi-repo ownership boundaries for `rektslug` and `nautilus_dev`
- [ ] T002 Freeze promotion gates `G0` through `G4`
- [ ] T003 Freeze required JSON schemas for smoke, soak, continuous, and recovery evidence
- [ ] T004 Freeze fail-closed conditions and account-flatness requirements

## Phase 2: Long Soak

- [ ] T005 Define review-grade soak profiles:
  - short: `2` cycles for development smoke
  - standard: `20` cycles for pre-review
  - extended: `50` cycles or time-bounded equivalent for release evidence
- [ ] T006 Add or verify aggregate metrics in the soak report:
  `passed_cycles`, `failed_cycles`, `feedback_rows`, `open_positions`,
  `open_orders`, `cleanup_count`, `total_pnl`, per-cycle latency
- [ ] T007 Run standard soak on Hyperliquid testnet and retain aggregate JSON
- [ ] T008 Run extended soak or document why standard soak is the accepted gate
- [ ] T009 Update runbook with accepted soak profile, command, and evidence path

## Phase 3: Real-Signal Continuous Paper/Testnet Mode

- [ ] T010 Define continuous-mode runtime config:
  symbol allowlist, minimum confidence, max size, max accepted signals,
  max runtime window, and dry-run/testnet execution mode
- [ ] T011 Implement or wire dry-run real-signal consumer that records decisions
  without venue orders
- [ ] T012 Implement or wire testnet real-signal consumer with conservative
  execution controls
- [ ] T013 Persist lifecycle state for every observed signal:
  `received`, `rejected`, `accepted`, `order_submitted`, `order_rejected`,
  `filled`, `position_opened`, `position_closed`, `feedback_published`,
  `feedback_persisted`
- [ ] T014 Run continuous dry-run over a bounded real-signal window and retain report
- [ ] T015 Run continuous testnet/paper over a bounded real-signal window and retain report

## Phase 4: Recovery And Fault Injection

- [ ] T016 Define supported fault-injection points:
  pre-submit, post-submit/pre-fill, open-position/pre-close,
  post-close/pre-feedback, Redis unavailable, DuckDB unavailable
- [ ] T017 Add deterministic test hooks or controlled script flags for each fault point
- [ ] T018 Verify restart recovery for post-submit/pre-fill
- [ ] T019 Verify restart recovery for open-position/pre-close
- [ ] T020 Verify restart recovery for post-close/pre-feedback
- [ ] T021 Verify Redis unavailable path fails closed and preserves retryable feedback where applicable
- [ ] T022 Verify DuckDB unavailable path fails closed and does not report success
- [ ] T023 Verify final account state is flat and has zero open orders after every recovery test

## Phase 5: Metrics And Review Evidence

- [ ] T024 Produce lifecycle metrics summary:
  signals seen, rejected, accepted, submitted, rejected orders, opened positions,
  closed positions, feedback published, feedback persisted, residual orders cleaned
- [ ] T025 Produce latency summary:
  signal-to-submit, submit-to-fill, open-to-close, close-to-feedback,
  feedback-to-persist
- [ ] T026 Produce final `EVIDENCE_PACKAGE.md`
- [ ] T027 Produce machine-readable `evidence_summary.json`
- [ ] T028 Update `docs/EXECUTION_READINESS_ROADMAP.md` with spec-037 result
- [ ] T029 Update `docs/EXECUTION_READINESS_EXTERNAL_REVIEW.md` with review entry points
- [ ] T030 Final review: confirm no secrets in logs, docs, JSON, or committed artifacts
- [ ] T031 Mark spec status implemented only after `G0` through `G4` are satisfied
