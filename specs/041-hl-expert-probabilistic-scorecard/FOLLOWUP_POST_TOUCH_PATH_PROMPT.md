Implement only the narrow post-touch path follow-up for `spec-041`.

Repository:
- `/media/sam/1TB/rektslug`

Do not open new scope.
Do not touch `nautilus_dev`.
Do not refactor unrelated scorecard modules.

Context:
- `spec-041` is review-closeable
- contracts, slicing, dominance rows, backfill entry point, and reproducibility are already in place
- one residual functional gap remains:
  - the real builder/pipeline path does not compute post-touch `mfe_bps` / `mae_bps`
  - `POST_TOUCH_WINDOW_HOURS` is defined but unused

Goal:
Implement a narrow `apply_post_touch_path()` stage so the real pipeline populates:
- `mfe_bps`
- `mae_bps`

from realized post-touch price action after first touch.

Authoritative files:
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/spec.md`
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/tasks.md`
- `/media/sam/1TB/rektslug/specs/041-hl-expert-probabilistic-scorecard/IMPLEMENTATION_REPORT.md`
- `/media/sam/1TB/rektslug/src/liquidationheatmap/models/scorecard.py`
- `/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/builder.py`
- `/media/sam/1TB/rektslug/src/liquidationheatmap/scorecard/pipeline.py`

Hard rules:
- implement only the post-touch path evaluator
- use the existing `POST_TOUCH_WINDOW_HOURS` constant
- preserve first-touch semantics
- keep `MFE/MAE` in integer bps
- do not add a global score or extra runtime ownership
- do not modify external API shape beyond populating existing fields

Required behavior:
1. For touched observations only, scan the realized price path from `touch_ts` until:
   - `touch_ts + POST_TOUCH_WINDOW_HOURS`
2. Compute:
   - `mfe_bps`
   - `mae_bps`
3. Respect side:
   - for `long`, favorable move is upward from `level_price`, adverse is downward
   - for `short`, favorable move is downward from `level_price`, adverse is upward
4. Leave untouched observations with:
   - `mfe_bps = None`
   - `mae_bps = None`
5. Keep the rest of the scorecard pipeline unchanged.

Required tests:
- RED first
- builder-level test for `long`
- builder-level test for `short`
- test that untouched rows remain null
- pipeline-level test proving real pipeline inputs yield non-zero `mfe/mae` quantiles when post-touch price path exists

Commit style:
- one commit only

Suggested commit message:
- `feat(scorecard): compute post-touch mfe and mae`

Final response format:
- Changed files
- Tests/checks run
- Commit hash
- Result
- Remaining risks or blockers
