# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Alpha Vantage stock trendline analysis project that processes S&P 500 and Russell stock data. The system fetches daily stock prices, calculates trendlines, and tracks price breakthroughs using logarithmic slope analysis.

## Core Architecture

### Main Components

- **main.py**: Entry point that runs daily updates and performance profiling
- **daily.py**: Daily data processing pipeline for all tickers in the database
- **db.py**: Database operations, Alpha Vantage fetching (parallel prefetch + rate limiter, split handling) and connection management with PostgreSQL
- **trendline_core.py**: Single source of truth for trendline math (vectorized numpy: best upper/under line, trendline projection, sequence)
- **methods.py**: Legacy CSV-based trendline utilities and chart plotting
- **historical_analysis.py / historical_pipeline.py**: Historical (point-in-time) trendline simulation for backtesting
- **scripts/**: Utility and one-time scripts (run as `python -m scripts.<name>` from the repo root): compute_betas, run_historical_analysis, populate_under_historical, truncate_and_reload, update_all_ticker_extremes
- **research/**: One-off analysis and test scripts (run as `python -m research.<name>`)

### Data Structure

- **alpha/**: Stock price CSV files (one per ticker: AAPL.csv, MSFT.csv, etc.)
- **alpha/status/**: Processed trendline status files with breakthrough analysis
- **alpha/plot/**: Generated chart visualizations with trendlines
- **data/**: Ticker list CSVs (nasdaq100, s&p, russell, iwm)
- **sql/**: Table creation / maintenance SQL scripts
- **docs/**: One-off summaries and pipeline notes
- **research/output/**: Outputs written by research scripts (sentiment CSVs, portfolio plots, etc.)
- Runtime state CSVs stay in the repo root (`positions.csv`, `open_positions.csv`, `trendlines.csv`) — core code reads/writes them by relative path
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

- API key: read from `.env` (`ALPHA_VANTAGE_KEY`) — never hardcode it
- Rate limiting: shared token-bucket limiter, `ALPHA_VANTAGE_RPM` in `.env` (default 75/min; set to your plan tier)
- Daily updates use `outputsize=compact` (last ~100 days); full history fetched only for new tickers, large gaps, or when a split is detected
- Split handling: when a split day appears in new data, the ticker's entire price history and status tables are reloaded/cleared so all prices share one scale

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