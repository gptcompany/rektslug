# NT Service Enablement Prompt

Use this prompt for the `nautilus_dev` team.

This is **not** a design task. The service definitions already exist. The only
goal is to install, enable, verify, and close the loop professionally without
scope creep.

## Copy/Paste Prompt

```text
Implement only the final service enablement pass for the unified cockpit runtime.

Repository:
- /media/sam/1TB/nautilus_dev

Reference:
- /media/sam/1TB/rektslug/specs/040-nautilus-continuous-paper-testnet/NAUTILUS_DEV_RUNTIME_PERSISTENCE_HANDOFF.md

Facts already verified:
- rektslug is no longer the blocker
- these unit files already exist in nautilus_dev/config:
  - nt-liquidation-continuous.service
  - nt-strategic-controller.service
  - operator-cockpit.service
- the unified cockpit goes HEALTHY when L2 + L3 are alive together
- the missing step is operational enablement, not new architecture

Your task:
1. Review the existing three unit files only for correctness and minimal fixes.
2. If needed, make only minimal edits required for installation and runtime correctness.
3. Install the units on the host.
4. daemon-reload
5. enable --now the required services
6. verify they stay up
7. run the unified cockpit builder check
8. stop

Strict scope:
- no new features
- no redesign
- no new UI
- no rektslug changes
- no ownership changes
- no speculative refactors
- no unrelated cleanup in nautilus_dev

Allowed files:
- config/nt-liquidation-continuous.service
- config/nt-strategic-controller.service
- config/operator-cockpit.service
- optional install helper if and only if strictly needed for these 3 services
- minimal docs/runbook note if and only if you changed install procedure

Not allowed:
- changing strategy logic
- changing cockpit semantics
- changing readiness ownership
- changing browser payload contracts
- touching unrelated dirty files

Acceptance criteria:
1. `systemctl status nt-liquidation-continuous.service --no-pager` shows active/running
2. `systemctl status nt-strategic-controller.service --no-pager` shows active/running
3. `systemctl status operator-cockpit.service --no-pager` shows active/running
4. local runtime artifacts are fresh:
   - runtime/portfolio-runtime-snapshot.json
   - runtime/operator-connectivity-status.json
   - runtime/operator-risk-status.json
   - runtime/strategic-controller-status.json
5. unified builder returns:
   - overall_status = HEALTHY
   - readiness.ready = true
   - blocking_card_ids = []
   - critical_blockers = []

Required verification command:
cd /media/sam/1TB/nautilus_dev
dotenvx run -f /media/sam/1TB/.env -- uv run python - <<'PY'
from pathlib import Path
from operator_cockpit.api import build_browser_state
import json
payload = build_browser_state(
    project_root=Path('.'),
    rektslug_base_url='http://127.0.0.1:8002',
    catastrophe_drill_passed=True,
    restart_clean=True,
)
print(json.dumps({
    'overall_status': payload.get('overall_status'),
    'readiness_ready': payload.get('readiness', {}).get('ready'),
    'blocking_card_ids': payload.get('readiness', {}).get('details', {}).get('blocking_card_ids'),
    'critical_blockers': payload.get('readiness', {}).get('critical_blockers'),
}, indent=2, sort_keys=True, default=str))
PY

Rules:
- Make exactly one commit, then stop.
- If the existing unit files are already correct, do not over-edit them.
- If blocked, report the exact operational blocker only.
- Final response format:
  - Changed files
  - Commands run
  - Commit hash
  - Runtime verification
  - Remaining blockers
```
