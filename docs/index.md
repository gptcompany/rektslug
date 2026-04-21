# LiquidationHeatmap Documentation

Welcome to the LiquidationHeatmap documentation.

## Quick Start

See the repository
[README](https://github.com/gptcompany/rektslug/blob/master/README.md)
for installation instructions.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design.

## Production

See [Production E2E Status](PRODUCTION_E2E_STATUS.md) for the current enabled
runtime, systemd timers, validation evidence, and production boundary.

See [Production Checklist](PRODUCTION_CHECKLIST.md) for operational checks.

## API Reference

See [API Reference](api/index.md) for API documentation.

## Validation

See [Data Validation Guide](DATA_VALIDATION.md) for internal data-quality checks.

See [Provider API Comparison Workflow](provider-api-comparison.md) for external
provider capture and comparison (CoinAnk, Coinglass, Bitcoin CounterFlow).

See [Chart Routes](runbooks/chart-routes.md) for the canonical local/provider
liq-map validation matrix and browser entrypoints.

See [Parity Thresholds](runbooks/parity-thresholds.md) for the official gates
used for:

- `liq-map` visual similarity
- `liq-map` provider-data calibration
- future heatmap threshold policy

For the internal validation dashboard, use:

- [frontend/validation_dashboard.html](../frontend/validation_dashboard.html)
- `/api/validation/dashboard` from `src/api/endpoints/dashboard.py`

That dashboard is separate from the provider-parity workflow documented in
`provider-api-comparison.md`.
