# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Alpha Vantage stock trendline analysis project that processes S&P 500 and Russell stock data. The system fetches daily stock prices, calculates trendlines, and tracks price breakthroughs using logarithmic slope analysis.

## Core Architecture

### Main Components

- **main.py**: Entry point that runs daily updates and performance profiling
- **daily.py**: Daily data processing pipeline for all tickers in the database 
- **db.py**: Database operations and connection management with PostgreSQL
- **methods.py**: Core trendline calculation algorithms and Alpha Vantage API integration
- **scripts/compute_betas.py**: Beta calculation for stocks relative to SPY

### Data Structure

- **alpha/**: Stock price CSV files (one per ticker: AAPL.csv, MSFT.csv, etc.)
- **alpha/status/**: Processed trendline status files with breakthrough analysis
- **alpha/plot/**: Generated chart visualizations with trendlines
- **Database tables**: `stock_prices`, `tickers_russell`, `tickers` (PostgreSQL)

### Key Algorithms

The project uses logarithmic scale trendline analysis:
- Peak detection using scipy.signal.find_peaks
- Validation that no intermediate prices breach the trendline
- Frequency-based trendline ranking across different distance parameters
- Breakthrough detection when price crosses above established trendlines

## Development Commands

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Database connection requires .env file with:
# DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
```

### Running the System
```bash
# Full daily update pipeline
python main.py

# Individual components
python daily.py  # Update all tickers
python -c "from methods import plot_chart; plot_chart('AAPL')"  # Generate charts
```

### Database Operations
The system uses PostgreSQL with environment-based configuration. Key tables:
- `stock_prices`: Historical OHLC data
- `tickers_russell`: Russell index tickers
- `upper_trendlines`: Calculated trendline data

## Alpha Vantage API

- API key: '8LLD101ZZ48BBVC8' (hardcoded in methods.py:14)
- Rate limiting: 1-second delays between calls
- Fetches adjusted daily data with dividend/split normalization

## Performance Profiling

Built-in timing system in db.py tracks function execution:
- Uses @timed decorator for function-level profiling
- time_block context manager for code blocks
- Outputs to profile_times.csv

## Key Functions

- `methods.py:get_valid_negative_slope_trend_lines()`: Core trendline detection
- `methods.py:analyze_price_breakthrough()`: Breakthrough analysis
- `db.py:updateDBWithAPI()`: Fetch and store new price data
- `methods.py:plot_chart()`: Generate technical analysis charts

## Data Processing Flow

1. Fetch tickers from database (`tickers_russell` table)
2. Update price data via Alpha Vantage API
3. Calculate/update trendline status for each ticker
4. Check for breakthrough events on new trading days
5. Generate performance profiles and charts as needed