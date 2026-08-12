-- ============================================================
-- Clear all tables before re-running with split-adjusted data
-- ============================================================
-- Run this script to clear all price-dependent data before
-- running historical_pipeline.py with the new split-adjusted
-- fetch_full_historical_data function
-- ============================================================

-- Step 1: Clear source price data
TRUNCATE TABLE stock_prices CASCADE;

-- Step 2: Clear historical trendlines (calculated from stock_prices)
TRUNCATE TABLE upper_trendlines_historical CASCADE;
TRUNCATE TABLE under_trendlines_historical CASCADE;

-- Step 3: Clear historical status tables (depend on trendlines and prices)
-- Note: These might not exist yet, but include them if they do
DROP TABLE IF EXISTS upper_status_historical CASCADE;
DROP TABLE IF EXISTS under_status_historical CASCADE;

-- Step 4: Clear current/live trendlines (also calculated from stock_prices)
TRUNCATE TABLE upper_trendlines CASCADE;
TRUNCATE TABLE under_trendlines CASCADE;

-- Step 5: Clear current/live status tables
TRUNCATE TABLE upper_status CASCADE;
TRUNCATE TABLE under_status CASCADE;

-- Step 6: Clear ticker extremes (max/min prices depend on stock_prices)
DROP TABLE IF EXISTS ticker_extremes CASCADE;

-- Step 7: Clear multi-level trendline tracking tables (if they exist)
DROP TABLE IF EXISTS stock_dates CASCADE;
DROP TABLE IF EXISTS closest_trendline CASCADE;
DROP TABLE IF EXISTS closest_status CASCADE;

-- ============================================================
-- Keep these tables UNCHANGED (they don't depend on prices):
-- ============================================================
-- ✓ tickers (ticker list)
-- ✓ tickers_russell (Russell index tickers)
-- ============================================================

-- Verify tables are empty
SELECT 'stock_prices' as table_name, COUNT(*) as row_count FROM stock_prices
UNION ALL
SELECT 'upper_trendlines_historical', COUNT(*) FROM upper_trendlines_historical
UNION ALL
SELECT 'under_trendlines_historical', COUNT(*) FROM under_trendlines_historical
UNION ALL
SELECT 'upper_trendlines', COUNT(*) FROM upper_trendlines
UNION ALL
SELECT 'under_trendlines', COUNT(*) FROM under_trendlines
UNION ALL
SELECT 'upper_status', COUNT(*) FROM upper_status
UNION ALL
SELECT 'under_status', COUNT(*) FROM under_status;

-- Done! Now you can run historical_pipeline.py
