# Data Validation Guide

## Overview

This document describes the data quality validation process for aggTrades ingestion. Validation is performed **AFTER** ingestion completes to verify data integrity without impacting ingestion performance.

## Philosophy: Separation of Concerns

**Ingestion** (speed) ≠ **Validation** (quality)

- **Ingestion scripts** focus on speed and reliability (no validation overhead)
- **Validation scripts** run on-demand to verify data quality
- SQL-based checks leverage DuckDB's analytics performance

## Validation Script

### Location
`scripts/validate_aggtrades.py`

### Usage

```bash
# Validate default database
uv run python scripts/validate_aggtrades.py

# Validate specific database
uv run python scripts/validate_aggtrades.py --db /media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb
```

### Exit Codes
- `0`: All validation checks passed ✅
- `1`: One or more checks failed ❌

## Validation Checks

### 1. Basic Statistics 📊
Verifies database contains data and shows summary metrics:
- Total rows
- Date range (min/max timestamp)
- Number of symbols
- Price range (min/max)

**Pass criteria**: Database has > 0 rows

---

### 2. Duplicate Detection 🔍
Identifies duplicate trades based on business key:
- `(timestamp, symbol, price, quantity)`

**SQL Query**:
```sql
SELECT COUNT(*) as total_rows,
       COUNT(DISTINCT (timestamp, symbol, price, quantity)) as unique_rows
FROM aggtrades_history
```

**Pass criteria**: `total_rows == unique_rows`

**On failure**: Shows sample duplicates with count

**Prevention**: Use UNIQUE constraint + `ON CONFLICT DO NOTHING` (see migration script)

---

### 3. Invalid Values Check ⚠️
Detects data corruption or parsing errors:
- Negative or zero prices
- Negative or zero quantities
- NULL values in required fields

**Pass criteria**: No invalid values found

**Common causes**:
- CSV parsing errors
- Data corruption in source files
- Schema mismatch (wrong column mapping)

---

### 4. Temporal Continuity Check 📅
Identifies gaps in time series data:
- Missing days between min/max date range
- Shows gap size (number of missing days)

**Algorithm**:
```python
# Get all days with data
days = SELECT DATE(timestamp) FROM aggtrades_history GROUP BY DATE(timestamp)

# Check for gaps > 1 day between consecutive dates
for prev_date, current_date in pairs(days):
    gap = (current_date - prev_date).days - 1
    if gap > 0:
        report_gap(prev_date, current_date, gap)
```

**Pass criteria**: No gaps > 1 day

**Expected failures**:
- Binance downtime or maintenance windows
- Missing source CSV files
- Failed ingestion runs (check logs)

---

### 5. Sanity Checks 🧪
Validates realistic value ranges:

#### BTC Price Sanity
- Expected range: $100 - $1,000,000
- Flags trades outside this range

**Why**: Catches data corruption (wrong decimals, wrong symbol mapping)

#### Large Quantity Detection
- Threshold: > 10,000 BTC per trade
- Flags suspiciously large quantities

**Why**: Prevents statistical outliers from skewing heatmap calculations

**Pass criteria**: No unrealistic values found

---

## Example Output

```
═══════════════════════════════════════════
  aggTrades Data Validation Report
═══════════════════════════════════════════

Database: /media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb

📊 Basic Statistics
┌────────────┬──────────────────────────────────┐
│ Metric     │ Value                            │
├────────────┼──────────────────────────────────┤
│ Total Rows │ 297,009,159                      │
│ Date Range │ 2021-12-01 → 2024-10-31         │
│ Symbols    │ 1                                │
│ Price Range│ $15,476.01 → $73,777.00         │
└────────────┴──────────────────────────────────┘

🔍 Duplicate Detection
  ✅ No duplicates found

⚠️  Invalid Values Check
  ✅ All values valid

📅 Temporal Continuity Check
  Total days with data: 1,127
  ⚠️  Found 2 gap(s):
    2023-02-01 → 2023-03-01 (28 days missing)
    2022-02-01 → 2022-03-01 (28 days missing)

🧪 Sanity Checks
  ✅ All sanity checks passed

═══ Summary ═══
  Basic Stats: ✅ PASS
  Duplicates: ✅ PASS
  Invalid Values: ✅ PASS
  Temporal Continuity: ❌ FAIL
  Sanity Checks: ✅ PASS

Score: 4/5 checks passed

⚠️  Some checks failed - review data quality
```

## When to Run Validation

### Required
- ✅ After full historical ingestion
- ✅ Before migration (duplicate prevention)
- ✅ After re-running failed months

### Recommended
- After major schema changes
- When debugging calculation issues
- Before production deployment

### Optional
- After each incremental ingestion (adds overhead)
- In CI/CD pipeline (if test database available)

## Fixing Common Issues

### Duplicates Detected
**Solution**: Run migration script to add UNIQUE constraint
```bash
uv run python scripts/migrate_add_unique_constraint.py
```

### Temporal Gaps
**Diagnosis**: Check which months are missing
```bash
# List missing months from logs
grep "Error" /tmp/4year_ingestion.log
```

**Solution**: Re-run specific months with correct dates
```bash
# Example: Fix February 2023
uv run python scripts/ingest_aggtrades.py \
    --symbol BTCUSDT \
    --start-date 2023-02-01 \
    --end-date 2023-02-28 \
    --data-dir /path/to/data
```

### Invalid Values
**Diagnosis**: Check sample rows
```sql
-- Find problematic rows
SELECT * FROM aggtrades_history WHERE price <= 0 LIMIT 10;
```

**Solution**: Delete corrupt data and re-ingest
```sql
DELETE FROM aggtrades_history WHERE price <= 0 OR quantity <= 0;
```

## Integration with n8n Workflow

For automated ingestion via n8n:

1. **Enable duplicate prevention** (UNIQUE constraint)
2. **Use `ON CONFLICT DO NOTHING`** in streaming code
3. **Run validation** as final workflow step
4. **Alert on failures** via n8n notifications

Example n8n workflow:
```
[Scheduler] → [Ingest Month] → [Validate] → [Alert if failed]
                                    ↓
                              [SUCCESS/FAIL]
```

## Performance Notes

- Validation uses **read-only** connection (safe for concurrent use)
- SQL queries optimized with indexes (once added)
- Expected runtime: ~10-30 seconds for 300M rows
- No memory overhead (streaming SQL queries)

## Future Enhancements

Potential additions (YAGNI for now):
- [ ] Price volatility checks (detect flash crashes)
- [ ] Volume distribution analysis
- [ ] Cross-symbol consistency (when multi-symbol support added)
- [ ] Historical comparison (detect sudden data pattern changes)
