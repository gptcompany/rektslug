# Review Notes: spec-035 Nautilus Backtest Hardening

## Delivered Review Assets
- `samples/hyperliquid_replay_bundle.json`: retained replay bundle for Hyperliquid expert snapshots.
- `samples/modeled_snapshot_replay_bundle.json`: retained replay bundle for modeled-snapshot replay on Bybit.
- `tests/test_nautilus_backtest_hardening.py`: round-trip tests for replay bundles and machine-readable result artifacts.

## Known Limitations
- Native `nautilus_trader` execution still requires a Python 3.12+ runtime.
- The sample replay bundles are audit inputs; they are not claims of full engine execution inside this Python 3.10 environment.
- Strategy logic remains intentionally simple and should be reviewed as harness validation, not alpha research.
- Fill, fee, and funding assumptions are explicit in the replay bundle but still depend on reviewer acceptance of the chosen constants.

## External Review Order
1. Review `src/liquidationheatmap/nautilus/backtest.py` for bundle/result serialization helpers.
2. Review `tests/test_nautilus_backtest_hardening.py` for round-trip coverage.
3. Inspect the sample bundles in `samples/` for auditability and provenance completeness.
