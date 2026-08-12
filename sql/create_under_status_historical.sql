-- Create table for historical lower status tracking
-- This table stores the daily status metrics for lower (support) trendlines
-- Mirrors the structure of upper_status_historical but for support lines

CREATE TABLE IF NOT EXISTS under_status_historical (
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    trendline NUMERIC(10, 2) NOT NULL,
    distance NUMERIC(10, 4) NOT NULL,
    breakthrough BOOLEAN NOT NULL,
    duration_from_date1 INTEGER NOT NULL,
    duration_from_date2 INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    update_trendline BOOLEAN NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date)
);

-- Add indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_under_status_historical_ticker ON under_status_historical(ticker);
CREATE INDEX IF NOT EXISTS idx_under_status_historical_date ON under_status_historical(date);
CREATE INDEX IF NOT EXISTS idx_under_status_historical_ticker_date ON under_status_historical(ticker, date);
CREATE INDEX IF NOT EXISTS idx_under_status_historical_breakthrough ON under_status_historical(breakthrough);
CREATE INDEX IF NOT EXISTS idx_under_status_historical_update_trendline ON under_status_historical(update_trendline);

-- Add comment to table
COMMENT ON TABLE under_status_historical IS 'Stores daily historical status metrics for lower (support) trendlines. Each row represents the trendline status for a specific ticker on a specific date, using only data that would have been available on that date.';

-- Add column comments
COMMENT ON COLUMN under_status_historical.ticker IS 'Stock ticker symbol';
COMMENT ON COLUMN under_status_historical.date IS 'The date for this status record';
COMMENT ON COLUMN under_status_historical.trendline IS 'The calculated lower trendline price for this date';
COMMENT ON COLUMN under_status_historical.distance IS 'Percentage distance from close price to trendline: ((trendline - close) / close) * 100';
COMMENT ON COLUMN under_status_historical.breakthrough IS 'True if close price is below the trendline (breakthrough support)';
COMMENT ON COLUMN under_status_historical.duration_from_date1 IS 'Number of trading days from the first trendline point (lowest point)';
COMMENT ON COLUMN under_status_historical.duration_from_date2 IS 'Number of trading days from the second trendline point';
COMMENT ON COLUMN under_status_historical.sequence IS 'Count of consecutive days with breakthrough=true';
COMMENT ON COLUMN under_status_historical.update_trendline IS 'True if this date triggered a trendline recalculation';
