# LiquidationHeatmap

Calculate and visualize cryptocurrency liquidation levels from Binance futures data using DuckDB analytics and FastAPI REST endpoints. Leverages open-source models (py-liquidation-map) for battle-tested algorithms.

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

# Run FastAPI server
uv run uvicorn api.main:app --reload

# Open visualization
open http://localhost:8000/heatmap.html

# Run tests
uv run pytest
```

## Architecture

**3-Layer Design**:
1. **Data**: DuckDB (zero-copy CSV ingestion, fast analytics)
2. **API**: FastAPI (REST endpoints) + Redis (pub/sub streaming)
3. **Viz**: Plotly.js (interactive heatmaps)

See `CLAUDE.md` for detailed architecture and development workflow.

## Data Sources

- **Raw CSV**: `/media/sam/3TB-WDC/binance-history-data-downloader/data/` (HDD, read-only)
  - BTCUSDT/, ETHUSDT/: aggTrades, bookDepth, fundingRate, metrics (Open Interest)
- **Database**: `/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb` (NVMe, fast I/O)
  - Tables: aggtrades_history (4.1B rows), klines_*_history, open_interest_history
- **N8N Container**: `/workspace/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb`
- **Cache**: `data/cache/` (Redis snapshots, temporary files)

**Note**: Raw CSV is read-only on HDD. DuckDB database on NVMe is the single source of truth.

## Supported Trading Pairs

| Symbol | Status | Data Coverage | Notes |
|--------|--------|---------------|-------|
| **BTC/USDT** | ✅ Production | 2021-12-01 to present | Primary pair, full validation |
| **ETH/USDT** | ✅ Production | 2021-12-01 to present | Symbol-agnostic pipeline |

All pairs use identical liquidation formulas (Binance USDT-M perpetuals). The pipeline is fully symbol-agnostic - new pairs require only data ingestion, no code changes.

## Development

### Setup

```bash
# Clone repository
git clone <repo-url>
cd LiquidationHeatmap

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env
# Edit .env with your configuration
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

See `CLAUDE.md` for detailed TDD workflow.

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
├── src/              # Core application code
├── tests/            # Test suite
├── scripts/          # Utilities and batch jobs
│   ├── ingest_aggtrades.py        # Streaming ingestion
│   ├── check_ingestion_ready.py   # Pre-flight checks (production)
│   ├── validate_aggtrades.py      # Data quality validation
│   ├── migrate_add_unique_constraint.py     # Duplicate prevention
│   └── migrate_add_metadata_tracking.py     # Metadata logging
├── docs/             # Documentation
│   ├── DATA_VALIDATION.md         # Validation guide
│   └── PRODUCTION_CHECKLIST.md    # Production readiness
├── data/             # Data directory
│   ├── raw/          # Symlink to 3TB-WDC (read-only)
│   └── cache/        # Temporary cache
# Database: /media/sam/2TB-NVMe/liquidationheatmap_db/ (external NVMe)
├── frontend/         # Visualization (if applicable)
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
curl "http://localhost:8888/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=30"
```

### Binance Standard Model (Legacy)

Direct calculation from aggTrades history. May overestimate volumes by ~17x compared to industry standards.

**API Usage**:
```bash
curl "http://localhost:8888/liquidations/levels?symbol=BTCUSDT&model=binance_standard&timeframe=30"
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

## Key Features

- ✅ **Zero-copy CSV ingestion**: DuckDB loads 10GB in ~5 seconds
- ✅ **OpenInterest-based model**: Industry-accurate volumes (52s for 30-day)
- ✅ **Persistent cache**: 99.9996% data reduction (1.9B → 7K rows)
- ✅ **Binance liquidation formulas**: Leverage py-liquidation-map algorithms
- ✅ **Real-time streaming**: Redis pub/sub (Nautilus pattern)
- ✅ **Interactive heatmaps**: Plotly.js visualization (no build step)
- ✅ **Test-Driven Development**: TDD guard enforces 80% coverage

## References

- [py-liquidation-map](https://github.com/aoki-h-jp/py-liquidation-map) - Liquidation clustering
- [binance-liquidation-tracker](https://github.com/hgnx/binance-liquidation-tracker) - Real-time tracking
- [Binance Liquidation Guide](https://www.binance.com/en/support/faq/liquidation) - Official formulas

## License

MIT License

## API Endpoints

### Base URL
```
http://localhost:8000
```

### Available Endpoints

#### 1. Health Check
```bash
GET /health
```
Returns API status.

#### 2. Liquidation Levels
```bash
GET /liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=30
```
**Parameters**:
- `symbol`: Trading pair (default: BTCUSDT)
- `model`: Model type (`openinterest` | `binance_standard` | `ensemble`)
- `timeframe`: Lookback period in days (7 | 30 | 90, default: 30)

**Returns**: Long liquidations (below price) and short liquidations (above price).

**Examples**:
```bash
# OpenInterest model (recommended) - 30 days
curl "http://localhost:8888/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=30"

# Binance Standard model (legacy)
curl "http://localhost:8888/liquidations/levels?symbol=BTCUSDT&model=binance_standard&timeframe=30"
```

#### 3. Historical Liquidations
```bash
GET /liquidations/history?symbol=BTCUSDT&aggregate=true&start=2024-10-29T18:00:00
```
**Parameters**:
- `symbol`: Trading pair (default: BTCUSDT)
- `aggregate`: Group by timestamp and side (default: false)
- `start`: Start datetime (ISO format, optional)
- `end`: End datetime (ISO format, optional)

**Returns**: Historical liquidation records or aggregated data.

**Examples**:
```bash
# Aggregated data for time-series
curl "http://localhost:8000/liquidations/history?symbol=BTCUSDT&aggregate=true"

# Raw records with date filtering
curl "http://localhost:8000/liquidations/history?symbol=BTCUSDT&start=2024-10-01&end=2024-10-31"
```

#### 4. Liquidation Heatmap
```bash
GET /liquidations/heatmap?symbol=BTCUSDT&model=binance_standard
```
**Parameters**:
- `symbol`: Trading pair (default: BTCUSDT)
- `model`: Model type (`binance_standard` | `ensemble`)
- `timeframe`: Time bucket (1h|4h|12h|1d|7d|30d, default: 1d)

**Returns**: Pre-aggregated heatmap data with density and volume per time+price bucket.

**Example**:
```bash
curl "http://localhost:8000/liquidations/heatmap?symbol=BTCUSDT&model=ensemble"
```

## Frontend Visualizations

### 1. Liquidation Map
```bash
open frontend/liquidation_map.html
```
Bar chart showing liquidation levels by price and leverage tier (Coinglass-style).

### 2. Historical Liquidations
```bash
open frontend/historical_liquidations.html
```
Time-series chart of liquidation volume over time with dual-axis (longs/shorts).

### 3. Liquidation Heatmap
```bash
open frontend/heatmap.html
```
2D heatmap (time × price) showing liquidation density with color gradient.

## Features

✅ **Liquidation Models**:
- Binance Standard (95% accuracy)
- Funding-Adjusted (experimental)
- Ensemble (weighted average)

✅ **Data Ingestion**:
- DuckDB zero-copy CSV loading (<5s per 10GB)
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

**Test Coverage**: 36% (target: ≥80%)

## Project Status

**Completed** (37/51 tasks, 73%):
- ✅ Phase 1: Setup
- ✅ Phase 2: Data Layer  
- ✅ Phase 3: Liquidation Calculation (MVP)
- ✅ Phase 4: Visualization (88%)
- ✅ Phase 7: Polish (retry, logging, tests)

**Pending**:
- ⏳ Phase 5: Model Comparison (US3)
- 🔮 Phase 6: Nautilus Integration (US4, future)

See `.specify/tasks.md` for detailed task list.

## License

MIT License
