# Spec-039 Validation Evidence Note

**Validation Run (2026-04-20)**
1. **Container Runtime Path Fix**: Rebuilt images with `DuckDBLifecycleStore` environment fix (`HEATMAP_DB_PATH`). Verified logs show zero `IO Error` when saving lifecycle state.
2. **Multi-symbol Publication**: Producer successfully published snapshot signals to `liquidation:signals:BTCUSDT` and `liquidation:signals:ETHUSDT`.
3. **Consumer Subscription**: The consumer correctly processed and accepted signals for both symbols.
4. **Report Persistence**: `shadow_report.json` was correctly written to the mounted volume, verifying `hypothetical_positions` and `circuit_breaker` state separately for both BTCUSDT and ETHUSDT.

Spec-039 is now fully verified.
