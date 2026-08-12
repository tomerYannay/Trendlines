# Ticker Extremes Tracking

## Overview

This module provides functionality to track and update the maximum HIGH and minimum LOW prices for each ticker in your database, along with the dates when these extremes occurred.

## Database Table

The `ticker_extremes` table stores:
- `ticker` (VARCHAR, PRIMARY KEY): Stock ticker symbol
- `max_price` (NUMERIC): Maximum HIGH price ever recorded
- `min_price` (NUMERIC): Minimum LOW price ever recorded
- `max_date` (DATE): Date when the maximum price occurred
- `min_date` (DATE): Date when the minimum price occurred
- `last_updated` (TIMESTAMP): When the record was last updated

## Setup

### 1. Create the Database Table

Run the SQL script to create the table:

```bash
psql -U your_username -d your_database -f create_ticker_extremes_table.sql
```

Or create the table programmatically using the test script:

```bash
python3 test_ticker_extremes.py
```

## Usage

### Method 1: Update a Single Ticker

```python
from historical_analysis import update_ticker_extremes

# Update extremes for a single ticker
update_ticker_extremes("AAPL")
```

### Method 2: Update All Tickers

```python
from historical_analysis import update_all_ticker_extremes

# Update extremes for all tickers in the tickers table
update_all_ticker_extremes()
```

## Functions

### `update_ticker_extremes(ticker)`

**Purpose**: Calculate and update the MAX(high) and MIN(low) for a given ticker.

**Parameters**:
- `ticker` (str): The ticker symbol to update

**Behavior**:
- Queries all historical prices for the ticker from `stock_prices` table
- Calculates the maximum HIGH and minimum LOW prices
- Identifies the dates when these extremes occurred
- Only updates the database if values have changed (efficient)
- Creates new record if ticker doesn't exist in `ticker_extremes`
- Updates existing record if new extremes are found

**Returns**: None (prints status messages)

**Example**:
```python
update_ticker_extremes("MSFT")
# Output: Inserted extremes for MSFT: MAX=468.35 on 2024-07-09, MIN=0.06 on 1986-03-13
```

### `update_all_ticker_extremes()`

**Purpose**: Update extremes for all tickers in the `tickers` table.

**Parameters**: None

**Behavior**:
- Fetches all tickers from the `tickers` table
- Calls `update_ticker_extremes()` for each ticker
- Handles errors gracefully (continues if one ticker fails)
- Provides progress updates

**Returns**: None (prints progress and status messages)

**Example**:
```python
update_all_ticker_extremes()
# Output:
# Processing 505 tickers for extreme price updates...
# Inserted extremes for AAPL: MAX=237.23 on 2024-12-26, MIN=0.05 on 1980-12-12
# Updated extremes for MSFT: MAX=468.35 on 2024-07-09, MIN=0.06 on 1986-03-13
# ...
# Completed extreme price updates for all tickers.
```

## Performance

Both functions are decorated with `@timed()` for performance profiling:
- Execution times are tracked in the profiling system
- Results can be analyzed in `profile_times.csv`

## Integration with Existing Pipeline

You can integrate this into your daily update pipeline by adding it to your main processing script:

```python
# In daily.py or main.py
from historical_analysis import update_all_ticker_extremes

def daily_update():
    # ... existing update code ...

    # Update ticker extremes
    print("Updating ticker extremes...")
    update_all_ticker_extremes()

    # ... continue with other processing ...
```

## Testing

Run the test script to verify the implementation:

```bash
python3 test_ticker_extremes.py
```

The test script will:
1. Create the `ticker_extremes` table if it doesn't exist
2. Test with a sample ticker from your database
3. Verify the data was inserted correctly
4. Display the results

## Query Examples

### View all extremes

```sql
SELECT * FROM ticker_extremes ORDER BY ticker;
```

### Find tickers with highest price range

```sql
SELECT
    ticker,
    max_price,
    min_price,
    ROUND(((max_price - min_price) / min_price * 100)::numeric, 2) as price_range_pct
FROM ticker_extremes
ORDER BY price_range_pct DESC
LIMIT 10;
```

### Find recent extremes

```sql
SELECT * FROM ticker_extremes
WHERE max_date >= CURRENT_DATE - INTERVAL '30 days'
   OR min_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY last_updated DESC;
```

## Notes

- The functions only update records when values actually change, making them efficient for daily runs
- All price calculations use the `high` column for max prices and `low` column for min prices
- Dates are stored as DATE type (no time component)
- The `last_updated` timestamp is automatically set by the database
