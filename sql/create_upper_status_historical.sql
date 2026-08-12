-- Create table for historical upper status tracking
-- This table stores the daily status metrics for upper (resistance) trendlines
-- Mirrors the structure of under_status_historical but for resistance lines

CREATE TABLE IF NOT EXISTS upper_status_historical (
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
CREATE INDEX IF NOT EXISTS idx_upper_status_historical_ticker ON upper_status_historical(ticker);
CREATE INDEX IF NOT EXISTS idx_upper_status_historical_date ON upper_status_historical(date);
CREATE INDEX IF NOT EXISTS idx_upper_status_historical_ticker_date ON upper_status_historical(ticker, date);
CREATE INDEX IF NOT EXISTS idx_upper_status_historical_breakthrough ON upper_status_historical(breakthrough);
CREATE INDEX IF NOT EXISTS idx_upper_status_historical_update_trendline ON upper_status_historical(update_trendline);

-- Add comment to table
COMMENT ON TABLE upper_status_historical IS 'Stores daily historical status metrics for upper (resistance) trendlines. Each row represents the trendline status for a specific ticker on a specific date, using only data that would have been available on that date.';

-- Add column comments
COMMENT ON COLUMN upper_status_historical.ticker IS 'Stock ticker symbol';
COMMENT ON COLUMN upper_status_historical.date IS 'The date for this status record';
COMMENT ON COLUMN upper_status_historical.trendline IS 'The calculated upper trendline price for this date';
COMMENT ON COLUMN upper_status_historical.distance IS 'Percentage distance from close price to trendline: ((trendline - close) / close) * 100';
COMMENT ON COLUMN upper_status_historical.breakthrough IS 'True if close price is above the trendline (breakthrough resistance)';
COMMENT ON COLUMN upper_status_historical.duration_from_date1 IS 'Number of trading days from the first trendline point (highest point)';
COMMENT ON COLUMN upper_status_historical.duration_from_date2 IS 'Number of trading days from the second trendline point';
COMMENT ON COLUMN upper_status_historical.sequence IS 'Count of consecutive days with breakthrough=true';
COMMENT ON COLUMN upper_status_historical.update_trendline IS 'True if this date triggered a trendline recalculation';
