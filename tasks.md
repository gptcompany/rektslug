# Tasks - LiquidationHeatmap

## ✅ Completed (2025-11-02): Critical Database Rebuild

### Problem Identified
Production-critical data quality issues discovered before N8N automation deployment:

**CRITICAL #1**: Using auto-increment ID instead of original `agg_trade_id`
- **Impact**: Re-ingesting same data creates duplicates (fatal for daily automation)
- **Root Cause**: `row_number() OVER (ORDER BY transact_time) + {max_id}` instead of CSV's `agg_trade_id`

**CRITICAL #2**: No deduplication guarantee
- **Impact**: `INSERT OR IGNORE` doesn't work without UNIQUE constraint
- **Root Cause**: Table had no PRIMARY KEY or UNIQUE constraint

**MEDIUM**: Throttle too aggressive for HDD safety
- **Impact**: PC almost crashed during ingestion (3TB WDC HDD saturation)
- **Current**: 100ms → **Required**: 200ms for production safety

### Solution Implemented

#### 1. Database Schema Rebuild
```sql
-- Old schema (BROKEN)
CREATE TABLE aggtrades_history (
    id BIGINT,  -- Auto-increment (NOT from CSV!)
    ...
)

-- New schema (PRODUCTION-READY)
CREATE TABLE aggtrades_history (
    agg_trade_id BIGINT PRIMARY KEY,  -- From CSV, ensures uniqueness
    timestamp TIMESTAMP NOT NULL,
    symbol VARCHAR NOT NULL,
    price DECIMAL(18, 8) NOT NULL,
    quantity DECIMAL(18, 8) NOT NULL,
    side VARCHAR NOT NULL,
    gross_value DOUBLE NOT NULL
)
```

**Script**: `/tmp/rebuild_db_with_pk_auto.py`
- ✅ Dropped old table (1,982,554,380 rows)
- ✅ Created new schema with PRIMARY KEY on `agg_trade_id`
- ✅ Added indexes on `timestamp` and `(timestamp, symbol)`

#### 2. Ingestion Code Fixes
**File**: `src/liquidationheatmap/ingestion/aggtrades_streaming.py`

**Changes**:
```python
# Fix #1: Use original agg_trade_id from CSV
# OLD:
row_number() OVER (ORDER BY transact_time) + {max_id} AS id

# NEW:
agg_trade_id  # Direct from CSV column

# Fix #2: Increase throttle for HDD safety
THROTTLE_MS = 200  # Was 100

# Fix #3: Update column list
(agg_trade_id, timestamp, symbol, ...)  # Was (id, timestamp, ...)
```

**Test Results**:
```
✅ Test successful: 4,734,015 rows inserted
Total rows: 4,734,015
agg_trade_id range: 1,965,151,407 → 1,969,885,421
```

#### 3. Unified Orchestrator (Ready for Production)
**Location**: `/tmp/ingest_full_history.py` (prototype)
**Production**: Will be `scripts/ingest_full_history.py` (after TDD tests)

**Single Command Usage**:
```bash
uv run python /tmp/ingest_full_history.py \
    --symbol BTCUSDT \
    --data-dir /media/sam/3TB-WDC/binance-history-data-downloader/data \
    --mode auto
```

**Features**:
- ✅ Auto-discovers all CSV files (2,131 files)
- ✅ Detects temporal gaps with SQL recursive CTE
- ✅ Fills gaps automatically with retry logic (3 attempts)
- ✅ Generates final summary report
- ✅ Idempotent (safe to re-run)
- ✅ HDD-safe with 200ms throttle

**Replaces**: 4+ manual steps (monthly iteration, gap detection, gap filling, validation)

### Files Created/Modified

**Created**:
- `/tmp/rebuild_db_with_pk_auto.py` - Database schema rebuild script
- `/tmp/ingest_full_history.py` - Unified orchestrator prototype
- `/tmp/ORCHESTRATOR_USAGE.md` - Complete documentation
- `/tmp/data_quality_analysis.py` - 10-point quality checks

**Modified**:
- `src/liquidationheatmap/ingestion/aggtrades_streaming.py` - Critical bug fixes
- `/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb` - Rebuilt with correct schema

### Next Steps

#### Pending Tasks
1. **Re-ingest all data** (2.13B rows) using unified orchestrator
   ```bash
   uv run python /tmp/ingest_full_history.py \
       --symbol BTCUSDT \
       --data-dir /media/sam/3TB-WDC/binance-history-data-downloader/data \
       --mode auto \
       --throttle-ms 200
   ```

2. **Validate data quality** after re-ingestion
   - Check for duplicates (should be 0)
   - Verify temporal continuity (no gaps)
   - Confirm agg_trade_id uniqueness

3. **Write TDD tests** for production version (required by TDD guard)
   - Test: agg_trade_id from CSV (not auto-increment)
   - Test: INSERT OR IGNORE with PRIMARY KEY prevents duplicates
   - Test: Throttle configuration
   - Test: Gap detection algorithm
   - Test: Retry logic

4. **Move to production** (after tests pass)
   - Move `/tmp/ingest_full_history.py` → `scripts/ingest_full_history.py`
   - Update CI/CD pipeline
   - Document in README.md
   - Configure N8N daily automation

### Production Readiness Checklist

- ✅ Database schema with PRIMARY KEY
- ✅ Ingestion code uses original agg_trade_id
- ✅ Throttle set to 200ms for HDD safety
- ✅ Idempotent ingestion (INSERT OR IGNORE)
- ✅ Unified orchestrator tested and working
- ⏳ Full data re-ingestion (pending)
- ⏳ Data quality validation (pending)
- ⏳ TDD tests (pending)
- ⏳ Production deployment (pending)

### User Emphasis
> "merda che entra = calcoli di merda che escono!" (garbage in = garbage out)

Data quality is **paramount** for liquidation map calculations. All critical bugs fixed before N8N automation.

---

## Future Tasks

### Short-term
- [ ] Complete full data re-ingestion (~2.13B rows)
- [ ] Run comprehensive data quality validation
- [ ] Write TDD tests for all new code
- [ ] Deploy unified orchestrator to production

### Long-term
- [ ] Add monitoring/alerting for N8N automation
- [ ] Implement incremental updates (vs full re-ingestion)
- [ ] Add support for multiple trading pairs (ETH, BNB, etc.)
- [ ] Create data quality dashboard

---

**Last Updated**: 2025-11-02
**Status**: Critical fixes completed, ready for re-ingestion
