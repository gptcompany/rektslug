# RektSlug

<p align="center">
  <img src="logo.png" alt="rektslug logo" width="800">
</p>

![CI](https://github.com/gptcompany/rektslug/actions/workflows/ci.yml/badge.svg?branch=master)
![Core Deploy](https://github.com/gptcompany/rektslug/actions/workflows/core-deploy.yml/badge.svg?branch=master)
![TechDocs](https://github.com/gptcompany/rektslug/actions/workflows/techdocs.yml/badge.svg?branch=master)
![Validation](https://github.com/gptcompany/rektslug/actions/workflows/validation.yml/badge.svg?branch=master)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square&logo=python)
![Issues](https://img.shields.io/github/issues/gptcompany/rektslug?style=flat-square)
![Last Commit](https://img.shields.io/github/last-commit/gptcompany/rektslug?style=flat-square)

Calculate and visualize cryptocurrency liquidation levels from Binance futures data using a QuestDB hot path, DuckDB analytical compute/cache paths, and FastAPI REST endpoints. Leverages open-source models (py-liquidation-map) for battle-tested algorithms.

Primary runtime configuration is now centralized in `src/liquidationheatmap/settings.py`, with shell wrappers loading the same environment contract through `scripts/lib/runtime_env.sh`. Environment overrides are documented in `.env.example`.

`rektslug` is the core production service: it owns the dashboard endpoints, signal-production path, shadow-validation loop, and feature API surface that downstream trading systems (including NT Trader) should consume. The upstream `ccxt-data-pipeline` remains an external collector; `rektslug` is responsible for syncing that upstream data into its local runtime stores and serving stable API contracts.

## Production Core Runtime

The production baseline now lives in this repo:

- `rektslug-api`: FastAPI core service
- `rektslug-sync`: near-real-time Parquet -> QuestDB gap-fill worker (5 minute loop by default, using DuckDB in-process for Parquet reads where needed)
- `redis`: internal pub/sub bus for signal transport
- `rektslug-shadow-producer`: Hyperliquid snapshot producer and Redis signal publisher
- `rektslug-shadow-consumer`: shadow-mode signal consumer with WebSocket liquidation correlation, circuit breaker checks, and report persistence
- `rektslug-feedback-consumer`: continuous execution-feedback persistence service writing to dedicated `signal_feedback.duckdb`

The continuous paper/testnet execution lane is now also closed through
`spec-040`, but it remains intentionally split across repositories:

- `rektslug`: signals, Redis contracts, feedback persistence, reporting, evidence
- `nautilus_dev`: Nautilus continuous execution runtime and venue lifecycle

Retained real G3 evidence lives in:

- `specs/040-nautilus-continuous-paper-testnet/EVIDENCE_PACKAGE.md`
- `specs/040-nautilus-continuous-paper-testnet/g3_session/20260422T212929Z/`

Host systemd timers are part of the production runtime:

- `lh-ingestion.timer`: daily ingestion
- `lh-ccxt-gap-fill.timer`: near-real-time ccxt gap fill
- `lh-hl-backfill-monitor.timer`: hourly Hyperliquid backfill batch monitor

Start the core runtime:

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Install or refresh production host timers:

```bash
sudo ./scripts/systemd/install.sh
systemctl list-timers lh-ingestion.timer lh-ccxt-gap-fill.timer lh-hl-backfill-monitor.timer --no-pager
```

Refresh or deploy an existing checkout:

```bash
bash scripts/deploy-core.sh
```

The `Core Deploy` GitHub Action builds and publishes the core image automatically whenever core code changes on `master`. If the deployment secrets are configured, the same workflow also performs a remote `docker compose pull && up -d` for the production stack.

Current production evidence and operational checks are documented in
[`docs/PRODUCTION_E2E_STATUS.md`](docs/PRODUCTION_E2E_STATUS.md).

## Quick Start

```bash
# Install dependencies
uv sync

# Pre-flight checks (recommended for production)
uv run python scripts/check_ingestion_ready.py \
    --db /media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb \
    --data-dir /media/sam/3TB-WDC/binance-history-data-downloader/data

# Ingest historical CSV data (example: Jan 2025)
uv run python scripts/ingest_aggtrades.py \
    --symbol BTCUSDT \
    --start-date 2025-01-01 \
    --end-date 2025-01-31 \
    --db /media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb \
    --data-dir /media/sam/3TB-WDC/binance-history-data-downloader/data

# Validate data quality (after ingestion)
uv run python scripts/validate_aggtrades.py

# Run FastAPI server (development)
uv run uvicorn src.liquidationheatmap.api.main:app --host ${HEATMAP_HOST:-0.0.0.0} --port ${HEATMAP_PORT:-8002}

# Open active chart route (phase 1)
open http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w

# Run tests
uv run pytest
```

## Canonical Chart Routes

Use these routes for validation, screenshots, and automation loops.

Active baseline (phase 1, current validation target):
- `http://localhost:8002/chart/derivatives/liq-map/<exchange>/<symbol>/1d`
- `http://localhost:8002/chart/derivatives/liq-map/<exchange>/<symbol>/1w`

Implemented but deferred until phase 2:
- `http://localhost:8002/chart/derivatives/liq-heat-map/<symbol>/1d`
- `http://localhost:8002/chart/derivatives/liq-heat-map/<symbol>/1w`

Current `liq-map` reference set for the active Binance baseline:

- Coinank:
  `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1d`
- Coinank:
  `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- Coinank:
  `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1d`
- Coinank:
  `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1w`
- Local:
  `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- Local:
  `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- Local:
  `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- Local:
  `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`

Only `1d` and `1w` are supported right now. Other chart timeframes are intentionally out of scope until the 1:1 validation work is stable.

Legacy aliases still exist for compatibility (`/coinglass`, `/heatmap_30d.html`, `/liq_map_1w.html`), but they should no longer be treated as primary entrypoints.

## Architecture

**3-Layer Design**:
1. **Data**: QuestDB for hot/latest serving, DuckDB for analytical compute/cache/history
2. **API**: FastAPI (REST endpoints) + Redis (pub/sub streaming)
3. **Viz**: Plotly.js (interactive heatmaps)

See `ARCHITECTURE.md` for the repo summary and `docs/ARCHITECTURE.md` for the canonical architecture reference.

## Data Sources

- **Raw CSV**: `/media/sam/3TB-WDC/binance-history-data-downloader/data/` (HDD, read-only)
  - BTCUSDT/, ETHUSDT/: aggTrades, bookDepth, fundingRate, metrics (Open Interest)
- **QuestDB**: Hot serving store for latest market state and realtime API paths
- **DuckDB**: `/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb` (NVMe, fast I/O)
  - Used for analytical compute, historical coverage, and precomputed cache paths
- **N8N Container**: `/workspace/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb`
- **Cache**: `data/cache/` (Redis snapshots, temporary files)

**Note**: Raw CSV is read-only on HDD. QuestDB is the hot-path serving store; DuckDB remains the analytical engine and historical/cache store.

## Supported Trading Pairs

| Symbol | Status | Validation (F1 @ 1%) | Data Coverage | Tier Config |
|--------|--------|---------------------|---------------|-------------|
| **BTC/USDT** | ✅ Production | 77.8% | 2021-12-01 to present | `config/tiers/binance.yaml` |
| **ETH/USDT** | ✅ Production | 91.4% | 2021-12-01 to present | `config/tiers/ethusdt.yaml` |

All pairs use Binance USDT-M perpetual liquidation formulas. The pipeline is fully symbol-agnostic - new pairs require only data ingestion and tier config, no code changes. Each symbol has its own margin tier boundaries matching Binance's official tier structure.

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/gptcompany/rektslug.git
cd rektslug

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env
# Edit .env with your configuration

# Primary runtime settings are loaded from src/liquidationheatmap/settings.py
# and overridden via HEATMAP_* / CORS_* / RATE_LIMIT_* / LH_CACHE_* env vars
```

### Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run specific test
uv run pytest tests/test_module.py::test_function
```

### TDD Workflow

This project uses Test-Driven Development (TDD):

1. **RED**: Write failing test first
2. **GREEN**: Write minimal code to pass test
3. **REFACTOR**: Clean up code while tests pass

Follow the existing pytest suite and red-green-refactor discipline for TDD changes.

## Data Validation

After ingestion, validate data quality with:

```bash
uv run python scripts/validate_aggtrades.py
```

**Validation checks**:
- Basic statistics (row count, date range, price range)
- Duplicate detection
- Invalid values (negative prices, NULL fields)
- Temporal continuity (gap detection)
- Sanity checks (realistic value ranges)

See `docs/DATA_VALIDATION.md` for detailed documentation.

## Project Structure

```
LiquidationHeatmap/
├── archive/          # Historical reports and deprecated templates
├── src/              # Core application code
├── tests/            # Test suite
├── scripts/          # Utilities and batch jobs
│   ├── ingest_aggtrades.py        # Streaming ingestion
│   ├── check_ingestion_ready.py   # Pre-flight checks (production)
│   ├── validate_aggtrades.py      # Data quality validation
│   ├── lib/runtime_env.sh         # Shared shell runtime config
│   ├── migrate_add_unique_constraint.py     # Duplicate prevention
│   └── migrate_add_metadata_tracking.py     # Metadata logging
├── docs/             # Documentation
│   ├── DATA_VALIDATION.md         # Validation guide
│   └── PRODUCTION_CHECKLIST.md    # Production readiness
├── data/             # Data directory
│   ├── raw/          # Symlink to 3TB-WDC (read-only)
│   └── cache/        # Temporary cache
# Database: /media/sam/2TB-NVMe/liquidationheatmap_db/ (external NVMe)
├── frontend/         # Active UI pages + compatibility wrappers
│   └── legacy/       # Archived frontend implementations
├── CLAUDE.md         # Development guide for Claude Code
├── README.md         # This file
└── pyproject.toml    # Dependencies (UV)
```

## Contributing

1. Follow TDD workflow (see `CLAUDE.md`)
2. Run tests before committing
3. Format code with `ruff format .`
4. Lint code with `ruff check .`
5. Write clear commit messages (explain WHY, not just WHAT)

## Liquidation Models

### OpenInterest Model (Recommended)

Uses current Open Interest from Binance API and distributes it based on historical volume profile:

```python
volume_at_price = current_OI × (whale_volume_at_price / total_whale_volume)
```

**Parameters**:
- Lookback: 7/30/90 days (default: 30)
- Whale threshold: $500k+ trades only
- Bin size: Dynamic ($200/$500/$1500 based on timeframe)
- Leverage tiers: 5x(15%), 10x(30%), 25x(25%), 50x(20%), 100x(10%)

**Performance**: ~52 seconds for 30-day analysis
**Accuracy**: Matches Coinglass volumes (~2.6B long, ~4.2B short)

**API Usage**:
```bash
curl "http://localhost:8002/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=7"
```

### Binance Standard Model (Legacy)

Direct calculation from aggTrades history. May overestimate volumes by ~17x compared to industry standards.

**API Usage**:
```bash
curl "http://localhost:8002/liquidations/levels?symbol=BTCUSDT&model=binance_standard&timeframe=7"
```

---

## Cache Maintenance

The OpenInterest model uses a pre-aggregated `volume_profile_daily` table for fast queries (99.9996% data reduction: 1.9B → 7K rows).

### Setup Daily Updates

Run the setup script:
```bash
bash scripts/setup_cache_cronjob.sh
```

This will guide you through setting up a cron job that updates the cache daily at 00:05 UTC.

### Manual Cache Update

To manually update the cache:
```bash
uv run python scripts/create_volume_profile_cache.py
```

Expected output:
```
Creating volume_profile_daily table...
✅ Created volume_profile_daily with 7,345 rows
```

## Archive

Historical reports, session notes, and deprecated config templates are archived outside the repository root:

- `archive/reports/`
- `archive/config/`

**Cache Stats**:
- Rows: ~7,345 (from 1.9B raw trades)
- Size: ~500 KB
- Update time: ~30 seconds
- No server restart needed (DuckDB handles concurrent reads)

### Monitoring

Check cache update logs:
```bash
tail -f /var/log/liquidationheatmap/cache-update.log
```

---

## References

- [py-liquidation-map](https://github.com/aoki-h-jp/py-liquidation-map) - Liquidation clustering
- [binance-liquidation-tracker](https://github.com/hgnx/binance-liquidation-tracker) - Real-time tracking
- [Binance Liquidation Guide](https://www.binance.com/en/support/faq/liquidation) - Official formulas

## API Endpoints

### Base URL
```
http://localhost:8002
```

The canonical API/runtime contract now lives in `docs/ARCHITECTURE.md`, `docs/api_guide.md`, and `docs/QUESTDB_RUNTIME_BOUNDARY_MATRIX.md`. The summary below only lists the active endpoint families.

#### 1. Health Check
```bash
GET /health
```
Returns API status.

#### 2. Legacy Liquidation Levels
```bash
GET /liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=30
```
Legacy static levels endpoint kept for compatibility with the liq-map frontend and validation flows. This route still uses DuckDB analytical compute.

#### 3. Historical Liquidations
```bash
GET /liquidations/history?symbol=BTCUSDT&limit=100
```
QuestDB-backed liquidation history endpoint for recent records.

#### 4. Liquidation Heatmap
```bash
GET /liquidations/heatmap?symbol=BTCUSDT&model=binance_standard
```
QuestDB-backed latest-state lookup plus in-process model compute.

**Examples**:
```bash
curl "http://localhost:8002/liquidations/heatmap?symbol=BTCUSDT&model=ensemble"
curl "http://localhost:8002/liquidations/heatmap?symbol=ETHUSDT&model=binance_standard"
```

#### 5. Heatmap Timeseries
```bash
GET /liquidations/heatmap-timeseries?symbol=BTCUSDT&time_window=1d
```
Hybrid path:
- hot recent windows prefer QuestDB live reconstruction
- cold windows and precomputed cache paths still use DuckDB

#### 6. Market Data
```bash
GET /prices/klines?symbol=BTCUSDT&interval=5m&limit=100
GET /data/date-range?symbol=BTCUSDT
```
- `1m` and `5m` klines are QuestDB hot-path routes
- colder historical intervals remain separate historical paths

## Frontend Entry Points

Active UI targets (current workstream: `liq-map`):

- `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`

Deferred until phase 2 (`liq-heat-map` routes are implemented but not the active validation target):

- `http://localhost:8002/chart/derivatives/liq-heat-map/btcusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-heat-map/btcusdt/1w`
- `http://localhost:8002/chart/derivatives/liq-heat-map/ethusdt/1d`
- `http://localhost:8002/chart/derivatives/liq-heat-map/ethusdt/1w`

Legacy frontend implementations are archived under `frontend/legacy/`. The legacy filenames left in `frontend/` are compatibility wrappers only.

## Features

✅ **Liquidation Models**:
- Binance Standard (95% accuracy)
- Funding-Adjusted (experimental)
- Ensemble (weighted average)

✅ **Data Ingestion**:
- QuestDB hot-path ingestion for realtime serving
- DuckDB analytical ingestion/cache paths
- Open Interest & Funding Rate tracking
- Data validation & quality checks

✅ **API**:
- FastAPI REST endpoints
- Retry logic with exponential backoff
- Structured logging to `logs/liquidationheatmap.log`

✅ **Visualization**:
- Plotly.js interactive charts
- Coinglass color scheme (#d9024b, #45bf87, #f0b90b)
- Responsive design (mobile + desktop)

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Open coverage report
open htmlcov/index.html
```

## Current Scope

The active delivery scope is tracked in `CURRENT_SCOPE.md`.

- Phase 1: `liq-map` only
- Active baseline: Binance `BTCUSDT` and `ETHUSDT`
- Supported chart timeframes: `1d`, `1w`
- `liq-heat-map` remains implemented but deferred until the `liq-map` workstream is stable

Use `tasks.md` for the current task list and `CURRENT_SCOPE.md` for the operational boundary.
