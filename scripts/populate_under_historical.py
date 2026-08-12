"""
One-time script to populate lower (support) trendlines historical data.

This script is used to initially populate the under_trendlines_historical and
under_status_historical tables. The upper tables are already populated.

Pipeline:
1. Create lower trendlines for 2024-01-01 for ALL tickers
2. Update lower status for ALL tickers
"""

import numpy as np
import psycopg2
import pandas as pd
import time
from dotenv import load_dotenv
import os

# Import from our existing modules
from db import _add_profile_row, dump_profile_csv, find_and_update_under_trendline_historical
from historical_analysis import update_under_status_historical

# Load environment variables from the .env file
load_dotenv()

# Get the database credentials from the environment variables
db_username = os.getenv('DB_USERNAME')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')

db_config = {
    'dbname': db_name,
    'user': db_username,
    'password': db_password,
    'host': db_host,
    'port': db_port
}

connection = psycopg2.connect(**db_config)
cursor = connection.cursor()


def populate_under_historical_pipeline():
    """
    One-time pipeline to populate lower (support) trendlines historical data:
    1. Creates lower trendlines for 2024-01-01 for ALL tickers
    2. Updates lower status for ALL tickers

    Note: Upper trendlines and status are already populated.
    """
    start_time = time.time()
    print("🚀 Starting Lower Trendlines Historical Population Pipeline")
    print("=" * 60)

    # Fetch all tickers from the database
    cursor.execute("SELECT ticker FROM tickers;")
    rows = cursor.fetchall()
    tickers = [row[0] for row in rows]

    total_tickers = len(tickers)
    print(f"📊 Processing {total_tickers} tickers")
    print(f"📉 Focus: Lower (support) trendlines only")

    # Step 1: Create lower trendlines for 2024-01-01 for ALL tickers
    print("\n📉 Step 1: Creating lower (support) trendlines for 2024-01-01")
    print("-" * 50)

    analysis_date = "2024-01-01"

    failed_under_trendline_updates = []
    successful_under_trendline_updates = []

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:3d}/{total_tickers}] 📉 Creating lower trendline for {ticker}")
        try:
            t0 = time.perf_counter()
            find_and_update_under_trendline_historical(ticker, analysis_date)
            elapsed = time.perf_counter() - t0

            _add_profile_row("historical_under_trendlines", ticker, elapsed, ticker=ticker)
            successful_under_trendline_updates.append(ticker)
            print(f"              ✅ Completed in {elapsed:.2f}s")

        except Exception as e:
            print(f"              ❌ Error: {e}")
            failed_under_trendline_updates.append(ticker)
            continue

    print(f"\n📉 Lower Trendlines Summary:")
    print(f"   ✅ Successful: {len(successful_under_trendline_updates)}")
    print(f"   ❌ Failed: {len(failed_under_trendline_updates)}")

    if failed_under_trendline_updates:
        print(f"   Failed tickers: {', '.join(failed_under_trendline_updates[:10])}{'...' if len(failed_under_trendline_updates) > 10 else ''}")

    # Step 2: Update lower status for ALL tickers
    print("\n🔍 Step 2: Updating lower (support) status for all tickers")
    print("-" * 50)

    failed_under_status_updates = []
    successful_under_status_updates = []

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:3d}/{total_tickers}] 📉 Updating lower status for {ticker}")
        try:
            t0 = time.perf_counter()
            update_under_status_historical(ticker)
            elapsed = time.perf_counter() - t0

            _add_profile_row("historical_under_status", ticker, elapsed, ticker=ticker)
            successful_under_status_updates.append(ticker)
            print(f"              ✅ Completed in {elapsed:.2f}s")

        except Exception as e:
            print(f"              ❌ Error: {e}")
            failed_under_status_updates.append(ticker)
            continue

    print(f"\n🔍 Lower Status Summary:")
    print(f"   ✅ Successful: {len(successful_under_status_updates)}")
    print(f"   ❌ Failed: {len(failed_under_status_updates)}")

    if failed_under_status_updates:
        print(f"   Failed tickers: {', '.join(failed_under_status_updates[:10])}{'...' if len(failed_under_status_updates) > 10 else ''}")

    # Final Summary
    end_time = time.time()
    execution_time = end_time - start_time

    print("\n" + "=" * 60)
    print("🎯 PIPELINE COMPLETED")
    print("=" * 60)
    print(f"📊 Total tickers processed: {total_tickers}")
    print(f"📉 Lower trendlines created: {len(successful_under_trendline_updates)}")
    print(f"📉 Lower status updates completed: {len(successful_under_status_updates)}")

    # Print execution time
    if execution_time < 60:
        print(f"⏱️  Total execution time: {execution_time:.2f} seconds")
    elif execution_time < 3600:
        minutes = int(execution_time // 60)
        seconds = int(execution_time % 60)
        print(f"⏱️  Total execution time: {minutes:02}:{seconds:02}")
    else:
        hours = int(execution_time // 3600)
        minutes = int((execution_time % 3600) // 60)
        seconds = int(execution_time % 60)
        print(f"⏱️  Total execution time: {hours:02}:{minutes:02}:{seconds:02}")

    # Save profiling data
    try:
        dump_profile_csv("populate_under_historical_profile.csv")
        print(f"📝 Profiling data saved to populate_under_historical_profile.csv")
    except Exception as e:
        print(f"⚠️  Warning: Could not save profiling data: {e}")

    # Close database connection
    if connection:
        cursor.close()
        connection.close()
        print("🔐 Database connection closed")


if __name__ == "__main__":
    populate_under_historical_pipeline()
