import time

import psycopg2
from dotenv import load_dotenv
import os

from db import (
    updateDBWithAPI, update_upper_status, find_and_update_upper_trendline,
    check_and_update_upper_trendline, prefetch_daily_data, _add_profile_row,
)

# Load environment variables from the .env file
load_dotenv()

db_config = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
}

connection = psycopg2.connect(**db_config)
cursor = connection.cursor()


def daily_update(prefetch=True, max_workers=8, prefetch_outputsize='compact', tickers=None):
    """
    Update stock data for all tickers stored in the `tickers_russell` table.

    prefetch: fetch all API data in parallel up-front (rate-limited by
    ALPHA_VANTAGE_RPM), then run the DB pipeline per ticker on the
    already-downloaded data.
    prefetch_outputsize: 'compact' for routine daily runs; use 'full' for a
    catch-up run when the DB is more than ~100 trading days behind (avoids a
    second full fetch per ticker).
    tickers: optional explicit list (used for testing on a subset).
    """
    start_time = time.time()

    if tickers is None:
        cursor.execute("SELECT ticker FROM tickers_russell;")
        tickers = [row[0] for row in cursor.fetchall()]

    prefetched = prefetch_daily_data(tickers, outputsize=prefetch_outputsize, max_workers=max_workers) if prefetch else {}

    # Process each ticker
    for ticker in tickers:
        print(f"\n🟡 Updating {ticker}")
        try:
            t0 = time.perf_counter()
            updated_dates, is_new = updateDBWithAPI(ticker, prefetched_df=prefetched.get(ticker))
            if is_new:
                # A brand-new ticker has no anchored trendline yet
                find_and_update_upper_trendline(ticker)
            update_upper_status(ticker)
            if updated_dates:
                check_and_update_upper_trendline(ticker, updated_dates)
            _add_profile_row("ticker", "full_pipeline", time.perf_counter() - t0, ticker=ticker)
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            continue

    if connection:
        cursor.close()
        connection.close()

    execution_time = time.time() - start_time

    # Print the execution time in MM:SS or HH:MM:SS format
    if execution_time < 60:
        print(f"Execution time: {execution_time:.2f} seconds")
    elif execution_time < 3600:
        minutes = int(execution_time // 60)
        seconds = int(execution_time % 60)
        print(f"Execution time: {minutes:02}:{seconds:02}")
    else:
        hours = int(execution_time // 3600)
        minutes = int((execution_time % 3600) // 60)
        seconds = int(execution_time % 60)
        print(f"Execution time: {hours:02}:{minutes:02}:{seconds:02}")
