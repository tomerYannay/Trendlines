-- Create table for tracking max/min prices per ticker
CREATE TABLE IF NOT EXISTS ticker_extremes (
    ticker VARCHAR(10) PRIMARY KEY,
    max_price NUMERIC(10, 2) NOT NULL,
    min_price NUMERIC(10, 2) NOT NULL,
    max_date DATE NOT NULL,
    min_date DATE NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_ticker_extremes_ticker ON ticker_extremes(ticker);

-- Add comment to table
COMMENT ON TABLE ticker_extremes IS 'Tracks the maximum high and minimum low prices for each ticker with their respective dates';
