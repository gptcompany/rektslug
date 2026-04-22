# Gemini Implementation Prompt: spec-040

Use this file to ask Gemini to implement `spec-040` in bounded, reviewable
slices. This is intentionally not a one-shot "do everything" prompt.

## Spec Baseline

Before implementation, Gemini should treat these as the frozen spec baseline:

- `ebf671a specs: add spec-040 continuous paper-testnet runtime`
- `36794dc specs: tighten spec-040 acceptance and task coverage`

Review each implementation slice against those commits plus the current working
tree.

## How To Use This

Do **not** ask Gemini to implement the entire spec in one pass.

Use **one slice per invocation**. Each slice below has:

- exact task IDs
- repo boundary
- expected file areas
- required tests/checks
- exact stop condition
- exact commit message

Gemini works in YOLO mode unless constrained. This file is designed to prevent
that. The correct operating pattern is:

1. choose one slice
2. send Gemini the copy/paste prompt below with that slice filled in
3. let Gemini implement only that slice
4. review the commit
5. move to the next slice only after review

The operator should reject any Gemini pass that:

- spans multiple slices
- creates multiple commits
- edits both repos when the slice is single-repo
- marks future tasks complete
- claims live evidence without concrete runtime proof

## Copy/Paste Prompt

```text
You are implementing rektslug spec-040. This is not a review task.

Repositories:
- /media/sam/1TB/rektslug
- /media/sam/1TB/nautilus_dev

Spec files:
- /media/sam/1TB/rektslug/specs/040-nautilus-continuous-paper-testnet/spec.md
- /media/sam/1TB/rektslug/specs/040-nautilus-continuous-paper-testnet/plan.md
- /media/sam/1TB/rektslug/specs/040-nautilus-continuous-paper-testnet/tasks.md

Implementation target:
- Slice: <PASTE ONE SLICE NAME FROM THIS FILE>
- Tasks: <PASTE TASK IDS, FOR EXAMPLE T011R-T012>
- Commit message: <PASTE THE EXACT COMMIT MESSAGE FROM THIS FILE>

Frozen spec baseline to review against:
- ebf671a specs: add spec-040 continuous paper-testnet runtime
- 36794dc specs: tighten spec-040 acceptance and task coverage

Rules:
- Implement only the requested slice and then stop.
- Make exactly one commit for the slice, then stop.
- Do not start later slices.
- Follow TDD for tasks marked `RED`: add the failing test first, verify it
  fails for the intended reason, then implement the minimum code to pass.
- Do not modify unrelated files.
- Do not mark tasks complete unless the slice implementation and tests/checks
  are done.
- Preserve the frozen deployment boundary from spec-040:
  - `nautilus-liquidation-paper-testnet` stays outside `rektslug` as a
    `systemd-separated` service in `nautilus_dev`
  - `rektslug-feedback-consumer` stays a separate service in `rektslug`
    Docker Compose
- Do not absorb the Nautilus runtime into the `rektslug` core image.
- Do not merge the feedback consumer into `rektslug-shadow-consumer`.
- Use official NautilusTrader nightly docs as the primary source if runtime
  semantics are unclear. Do not rely on unofficial secondary sources for
  Nautilus behavior.
- Do not fake live evidence. If a slice depends on real Redis/testnet/runtime
  behavior that is unavailable, stop and report the blocker exactly.
- If blocked, stop and report:
  - exact blocker
  - repo + file/path
  - attempted command
  - what remains undone

Hard invariants:
- `rektslug` owns:
  - signal production
  - Redis signal/feedback contracts
  - feedback persistence into DuckDB
  - reporting, monitoring, and circuit breaker integration
- `nautilus_dev` owns:
  - Nautilus runtime process
  - venue connectivity
  - order lifecycle
  - execution reconciliation
- Continuous lifecycle states required by spec:
  - `received`
  - `rejected`
  - `accepted`
  - `order_submitted`
  - `order_rejected`
  - `order_filled`
  - `position_opened`
  - `position_closed`
  - `feedback_published`
  - `feedback_persisted`
  - `cleanup_verified`
- Minimum runtime outputs required by spec:
  - `signals_seen`
  - `signals_rejected`
  - `signals_accepted`
  - `orders_submitted`
  - `orders_rejected`
  - `orders_filled`
  - `positions_opened`
  - `positions_closed`
  - `feedback_published`
  - `feedback_persisted`
  - `residual_open_positions`
  - `residual_open_orders`
- Nautilus nightly constraints:
  - Python 3.12-3.14
  - standalone `TradingNode` service/process
  - one `TradingNode` per process
  - no notebook live runtime
  - no blocking work on the event loop

Final response format:
- Changed files
- Tests/checks run
- Commit hash
- Result
- Remaining risks or blockers
```

## Slices

Implement these in order unless explicitly instructed otherwise.

### Slice A: rektslug Feedback Consumer Service

Tasks:
- T011R
- T012

Repo:
- `/media/sam/1TB/rektslug`

Commit message:
- `feat(signals): add compose-managed feedback consumer service`

Goal:
- Turn the existing feedback consumer module into an actual production runtime
  service in `rektslug`.

Expected implementation:
- Reuse and extend existing code in:
  - `src/liquidationheatmap/signals/feedback.py`
  - `scripts/migrations/add_signal_feedback_table.sql`
  - `docker-compose.yml`
- Add any missing service wrapper needed for compose operation, for example:
  - `scripts/run-feedback-consumer.sh`
- Add or extend tests for:
  - always-on feedback consumption
  - persistence accounting
  - compose/service configuration if practical
- Keep the service separate from `rektslug-shadow-consumer`.
- Keep it on the `rektslug` side.

Suggested test/check set:

```bash
pytest -q tests/unit/test_feedback_consumer.py tests/integration/test_feedback_storage.py
pytest -q tests/test_shadow_compose_config.py
```

Stop condition:
- feedback consumer exists as a distinct compose-managed service
- RED tests added first and then pass
- one commit created
- stop

### Slice B: rektslug Measured Persistence Metrics And Interface Docs

Tasks:
- T013R
- T013
- T014
- T015
- T031B

Repo:
- `/media/sam/1TB/rektslug`

Commit message:
- `feat(signals): measure persisted feedback and define report contract`

Goal:
- Replace placeholder persistence/report semantics with measured values on the
  `rektslug` side and document the public interfaces.

Expected implementation:
- `feedback_persisted` must be counted from actual DuckDB writes, not inferred
  from logs
- define the machine-readable report contract required by spec-040
- document the public interfaces in repo docs:
  - feedback consumer Redis contract
  - continuous report JSON schema
  - healthcheck endpoints / health semantics
- update architecture docs if needed

Suggested file areas:
- `src/liquidationheatmap/signals/feedback.py`
- `docs/ARCHITECTURE.md`
- possibly a dedicated doc under `docs/`

Suggested test/check set:

```bash
pytest -q tests/unit/test_feedback_consumer.py tests/integration/test_feedback_storage.py
```

Stop condition:
- measured persistence accounting is implemented
- report contract is documented
- one commit created
- stop

### Slice C: nautilus_dev Continuous Service And Mode Guard

Tasks:
- T009B
- T016
- T017R
- T018R
- T018
- T019
- T020

Repo:
- `/media/sam/1TB/nautilus_dev`

Commit message:
- `feat(hyperliquid): add continuous paper-testnet runtime service`

Goal:
- Add the long-running continuous Nautilus paper/testnet runtime as a service,
  with explicit mode separation and Redis/feedback behavior.

Existing file areas to inspect first:
- `scripts/hyperliquid/run_live.py`
- `scripts/hyperliquid/liquidation_bridge_smoke.py`
- `scripts/hyperliquid/liquidation_bridge_soak.py`
- `configs/hyperliquid/testnet.py`
- `configs/hyperliquid/trading_node.py`
- `tests/hyperliquid/test_liquidation_bridge.py`

Expected implementation:
- add or wire a long-running service-grade runner instead of relying only on
  bounded wrappers
- implement explicit paper/testnet mode separation and fail-closed behavior
- add RED coverage first for:
  - runtime counters replacing placeholders
  - signal-from-Redis to feedback-published within timeout
- do not move this runtime into `rektslug`
- keep one `TradingNode` per process
- do not block the Nautilus event loop with persistence work

Suggested test/check set:

```bash
pytest -q tests/hyperliquid/test_liquidation_bridge.py
pytest -q tests/scripts/test_redis_connection.py
```

If there is an existing repo-specific lint/test command preferred by
`nautilus_dev`, use that instead and report it explicitly.

Stop condition:
- long-running service path exists in `nautilus_dev`
- mode guard exists and fails closed
- RED coverage added first and then passes
- one commit created
- stop

### Slice D: Recovery And Event-Loop Safety

Tasks:
- T021
- T022
- T023
- T024
- T025
- T026
- T026B

Repos:
- `/media/sam/1TB/rektslug`
- `/media/sam/1TB/nautilus_dev`

Commit message:
- `feat(runtime): harden continuous runtime recovery and fail-closed paths`

Goal:
- Make restart/recovery and fail-closed behavior explicit and measurable across
  the two-repo runtime boundary.

Expected implementation:
- verify or implement:
  - Nautilus service restart expectations
  - feedback consumer restart expectations
  - Redis unavailable fails closed
  - DuckDB unavailable fails closed
  - residual open positions/orders are explicitly checked
  - feedback publish/persist mismatch blocks green outcome
  - event loop is not blocked by feedback consumer / DuckDB writes
- If this slice becomes too large, stop and report which subtask needs to be
  split rather than silently broadening the change.

Suggested checks:
- repo-specific tests for touched files
- any runtime-latency measurement harness added for NFR-002

Stop condition:
- recovery/fail-closed code + checks for the requested slice are done
- one commit created
- stop

### Slice E: Live Evidence And Review Docs

Tasks:
- T027
- T028
- T029
- T030
- T031
- T032

Repos:
- `/media/sam/1TB/rektslug`
- `/media/sam/1TB/nautilus_dev`

Commit message:
- `docs(runtime): retain spec-040 evidence and review package`

Goal:
- Retain evidence and update review entry points after the runtime exists.

Important:
- Do not claim this slice is complete unless real runtime evidence was actually
  generated.
- If live Redis/testnet conditions are unavailable, stop and report the exact
  blocker rather than fabricating T027-T029.

Suggested outputs:
- updated execution-readiness docs
- evidence paths and summaries
- no secret leakage in committed artifacts

Stop condition:
- only if real evidence exists and docs are updated
- otherwise stop with blocker report

## Recommended Operator Sequence

Use Gemini in this order:

1. Slice A
2. Slice B
3. Slice C
4. Slice D
5. Slice E

Do not collapse A-D into one run. Slice E is allowed only after the runtime
exists and has been reviewed.
