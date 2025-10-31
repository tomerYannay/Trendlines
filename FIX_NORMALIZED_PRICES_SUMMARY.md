# Fix for Normalized Price Issue

## Problem Description

The stock_prices table was storing **normalized/adjusted** prices instead of **raw market prices**:

### API Response Example:
```json
"2021-09-03": {
    "1. open": "177.67",
    "2. high": "179.57",
    "3. low": "177.03",
    "4. close": "179.28",
    "5. adjusted close": "174.081894827552"
}
```

### What Was Happening (OLD CODE):
- Calculated normalization factor: `174.08 / 179.28 = 0.971`
- Applied to all prices:
  - open = 177.67 × 0.971 = 172.52
  - high = 179.57 × 0.971 = 174.36
  - low = 177.03 × 0.971 = 171.90
  - **close = 174.08 (adjusted close)**

### What Should Happen (FIXED CODE):
- Use raw market prices directly:
  - open = 177.67
  - high = 179.57
  - low = 177.03
  - **close = 179.28 (actual close, NOT adjusted)**

## Code Changes Made

### 1. File: `db.py` (Lines 269-277)

**Before:**
```python
# Calculate normalization factor for dividend/split adjustments
if close_price != 0:
    normalization_factor = adjusted_close / close_price
else:
    normalization_factor = 1.0

# Normalize all prices
normalized_open = round(open_price * normalization_factor, 2)
normalized_high = round(high_price * normalization_factor, 2)
normalized_low = round(low_price * normalization_factor, 2)
normalized_close = round(adjusted_close, 2)

rows.append((symbol, date_str, normalized_open, normalized_high, normalized_low, normalized_close, volume))
```

**After:**
```python
# Use actual prices without normalization
rows.append((symbol, date_str, round(open_price, 2), round(high_price, 2), round(low_price, 2), round(close_price, 2), volume))
```

### 2. File: `methods.py` (Lines 52-66)

Similar changes applied to `updateCSVWithAPI()` function.

## Impact

### Functions Affected:
- ✅ `db.py::fetch_full_historical_data()` - FIXED
- ✅ `db.py::updateDBWithAPI()` - FIXED (uses fetch_full_historical_data)
- ✅ `methods.py::updateCSVWithAPI()` - FIXED

### Pipeline Affected:
- ✅ `historical_pipeline.py` - Will use fixed code on next run

## How to Fix Existing Data

Your database currently contains normalized prices. To get raw prices:

### Option 1: Truncate and Reload (Recommended)

```bash
# 1. Connect to your database
psql -U your_username -d your_database

# 2. Truncate the table
TRUNCATE TABLE stock_prices;

# 3. Exit psql
\q

# 4. Re-run the pipeline (will use fixed code)
python3 historical_pipeline.py
```

### Option 2: Selective Reload

If you only want to reload specific tickers:

```bash
# 1. Delete specific tickers
psql -U your_username -d your_database

DELETE FROM stock_prices WHERE ticker IN ('A', 'AAPL', 'MSFT');

\q

# 2. The pipeline will automatically reload these tickers with raw prices
python3 historical_pipeline.py
```

### Option 3: Create a Reload Script

Use the provided script:

```bash
python3 truncate_and_reload.py
```

## Verification

After reloading, verify the fix worked:

```bash
python3 test_raw_prices.py
```

Expected output:
```
✅ Close price appears to be raw (non-normalized)
```

## Database Query to Check

```sql
-- Check a known example
SELECT ticker, date, open, high, low, close
FROM stock_prices
WHERE ticker = 'A' AND date = '2021-09-03';

-- Expected (after fix):
-- open: 177.67, high: 179.57, low: 177.03, close: 179.28

-- What you had (before fix):
-- open: 172.52, high: 174.36, low: 171.90, close: 174.08
```

## Why This Matters

1. **Trendline Calculations**: Your trendline analysis should use actual market prices, not adjusted prices
2. **Price Comparisons**: When comparing to current prices, you need consistent (raw) values
3. **Breakthrough Analysis**: Detecting when price crosses a trendline requires accurate prices
4. **Historical Analysis**: Your historical analysis should reflect actual trading prices

## Important Notes

- ✅ The code is now fixed - new data will be inserted correctly
- ⚠️ Existing data in the database is still normalized
- ⚠️ You need to reload existing data to get raw prices
- 💡 Make a backup before truncating
- 💡 The pipeline will automatically fetch full history for truncated tickers

## Timeline

1. **Before Fix**: Data was normalized using adjusted_close
2. **After Fix (now)**: Code uses raw market prices
3. **After Reload**: Database will have raw market prices
