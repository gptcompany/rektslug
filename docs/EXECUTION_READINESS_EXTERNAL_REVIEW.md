# External Review Summary: Execution Readiness Program

Date: 2026-04-17

## What This Review Covers

This review package now covers delivered follow-on work that moves the repo from
public `liq-map` and artifact serving into:

- deterministic historical replay for Bybit historical-only windows
- retained replay bundles for event-driven Nautilus backtesting
- paper/live runtime hardening with persisted status metrics and restart-safe state

## Delivered Review Assets

- roadmap document: [docs/EXECUTION_READINESS_ROADMAP.md](./EXECUTION_READINESS_ROADMAP.md)
- `spec-034` retained historical producer sample output:
  `specs/034-bybit-historical-producer-bridge/samples/bybit_historical_output/`
- `spec-035` retained replay bundles:
  - `specs/035-nautilus-event-driven-backtest-hardening/samples/hyperliquid_replay_bundle.json`
  - `specs/035-nautilus-event-driven-backtest-hardening/samples/modeled_snapshot_replay_bundle.json`
- `spec-035` review notes:
  `specs/035-nautilus-event-driven-backtest-hardening/REVIEW_NOTES.md`
- `spec-036` runtime evidence package:
  `specs/036-paper-live-trading-runtime-hardening/EVIDENCE_PACKAGE.md`

## Existing Tracks Still Open

- `spec-027`: Hyperliquid reserved-margin and portfolio-margin hardening
- `spec-015`: signal-loop downstream integration beyond the current bridge
- `spec-025` / `spec-011`: broader event distribution backlog

## Main Design Decisions Preserved

- source-data existence is not treated as equivalent to producer-readiness
- event-driven backtest hardening remains separate from paper/live trading hardening
- runtime safety controls remain explicit and reviewable before live deployment
- manifest-first and provenance-first design is preserved across all delivered follow-ons

## What External Reviewers Should Inspect First

1. `spec-034` sample historical output and the Bybit bridge tests.
2. `src/liquidationheatmap/nautilus/backtest.py` plus `tests/test_nautilus_backtest_hardening.py`.
3. `src/liquidationheatmap/runtime/executor.py`, `src/liquidationheatmap/signals/status_store.py`, and the signal/runtime tests.
4. `specs/036-paper-live-trading-runtime-hardening/rollout.md` and `EVIDENCE_PACKAGE.md`.

## Residual Environment Note

Native `nautilus_trader` execution still requires Python 3.12+ for real engine runs.
That is now an environment prerequisite, not an unfinished spec task in this repo.
