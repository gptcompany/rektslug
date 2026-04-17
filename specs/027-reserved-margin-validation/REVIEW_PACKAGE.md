# Portfolio-Margin Review Package

This package closes the repo-side delivery for `spec-027`.

Artifacts:
- `review_package.json`: offline summary generated from retained fixture and validation artifacts
- `data/validation/portfolio_margin_accounts_full.json`: observed PM account population snapshot
- `data/validation/portfolio_margin_repo_scan.json`: repo-wide address probe for additional PM accounts
- `tests/fixtures/hyperliquid/portfolio_margin_live_cases.json`: retained live-anchored PM fixture

Interpretation:
- The implementation is complete for PM detection, routing, solver math, and retained review evidence.
- The currently observable PM universe in local artifacts contains three PM accounts.
- Only one of those accounts currently exposes a comparable live `liquidationPx`; it remains within tolerance.
- The other two observed PM accounts are retained explicitly as non-comparable cases, so the repo does not pretend to have more live-comparable evidence than actually exists.
- The builder now checks that the retained fixture users, observed PM account artifact, and repo scan artifact all describe the same PM account set. A mismatch is treated as an error, not a silent partial package.

Regeneration:
```bash
uv run python scripts/build_portfolio_margin_review_package.py \
  --output specs/027-reserved-margin-validation/review_package.json
```
