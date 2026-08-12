-- Create table for historical lower trendlines analysis
-- This table stores lower (support) trendlines calculated for specific historical dates
-- Mirrors the structure of upper_trendlines_historical but for support lines

CREATE TABLE IF NOT EXISTS under_trendlines_historical (
    ticker VARCHAR(10) NOT NULL,
    analysis_date DATE NOT NULL,
    date1 DATE NOT NULL,
    date2 DATE NOT NULL,
    slope NUMERIC(10, 6) NOT NULL,
    date_diff INTEGER NOT NULL,
    index2 INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, analysis_date)
);

-- Add indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_under_trendlines_historical_ticker ON under_trendlines_historical(ticker);
CREATE INDEX IF NOT EXISTS idx_under_trendlines_historical_analysis_date ON under_trendlines_historical(analysis_date);
CREATE INDEX IF NOT EXISTS idx_under_trendlines_historical_ticker_analysis ON under_trendlines_historical(ticker, analysis_date);

-- Add comment to table
COMMENT ON TABLE under_trendlines_historical IS 'Stores historical lower (support) trendlines for backtesting and analysis. Each row represents the trendline that would have been calculated on a specific analysis_date using data available up to that date.';

-- Add column comments
COMMENT ON COLUMN under_trendlines_historical.ticker IS 'Stock ticker symbol';
COMMENT ON COLUMN under_trendlines_historical.analysis_date IS 'The date for which this trendline was calculated (using data up to this date)';
COMMENT ON COLUMN under_trendlines_historical.date1 IS 'First date (lowest point) of the trendline';
COMMENT ON COLUMN under_trendlines_historical.date2 IS 'Second date of the trendline';
COMMENT ON COLUMN under_trendlines_historical.slope IS 'Logarithmic slope of the trendline';
COMMENT ON COLUMN under_trendlines_historical.date_diff IS 'Number of trading days between date1 and date2';
COMMENT ON COLUMN under_trendlines_historical.index2 IS 'Index position of date2 in the trading days array';
