import numpy as np
import psycopg2
import pandas as pd
import time
from dotenv import load_dotenv
import os

# Import from our existing modules
from db import updateDBWithAPI, _add_profile_row, dump_profile_csv, find_and_update_under_trendline_historical
from historical_analysis import (
    find_and_update_upper_trendline_historical,
    update_upper_status_historical,
    update_under_status_historical,
    update_ticker_extremes
)

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


def historical_analysis_pipeline():
    """
    Historical analysis pipeline that:
    1. Updates all tickers with API data (from last DB date to today, or full history for new tickers)
    1.5. Updates ticker extremes (max/min prices) for successfully updated tickers
    2. Creates historical trendlines for 2024-01-01 (ONLY for new tickers from step 1)
       2a. Creates UPPER (resistance) trendlines
       2b. Creates LOWER (support) trendlines
    3. Updates historical status for ALL tickers
       3a. Updates UPPER (resistance) status
       3b. Updates LOWER (support) status
    """
    start_time = time.time()
    print("🚀 Starting Historical Analysis Pipeline")
    print("=" * 60)

    # Fetch all tickers from the Russell table
    cursor.execute("SELECT ticker FROM tickers;")
    rows = cursor.fetchall()
    tickers = [row[0] for row in rows]
    
    total_tickers = len(tickers)
    print(f"📊 Processing {total_tickers} tickers")
    
    # Step 1: Update all tickers with API data (full history for new tickers, incremental for existing)
    print("\n🔄 Step 1: Updating tickers with API data (from last DB date to today)")
    print("-" * 50)

    failed_api_updates = []
    successful_api_updates = []  # Initialize as empty list
    new_tickers = []  # Track tickers that had no previous data

    # print("\n⏩ Step 1: SKIPPED (running only Step 1.5 and Step 3)")

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:3d}/{total_tickers}] 🔄 Updating API data for {ticker}")
        try:
            t0 = time.perf_counter()
            updated_dates, is_new = updateDBWithAPI(ticker)
            elapsed = time.perf_counter() - t0

            _add_profile_row("api_update", ticker, elapsed, ticker=ticker)
            successful_api_updates.append(ticker)

            if is_new:
                new_tickers.append(ticker)
                print(f"              ✨ New ticker: Inserted {len(updated_dates)} historical records")
            elif updated_dates:
                print(f"              ✅ Updated {len(updated_dates)} new dates")
            else:
                print(f"              ℹ️  No new data")

        except Exception as e:
            print(f"              ❌ Error: {e}")
            connection.rollback()  # Rollback the failed transaction
            failed_api_updates.append(ticker)
            continue

    print(f"\n📈 API Update Summary:")
    print(f"   ✅ Successful: {len(successful_api_updates)}")
    print(f"   ✨ New tickers: {len(new_tickers)}")
    print(f"   ❌ Failed: {len(failed_api_updates)}")

    if new_tickers:
        print(f"   New tickers: {', '.join(new_tickers[:10])}{'...' if len(new_tickers) > 10 else ''}")

    if failed_api_updates:
        print(f"   Failed tickers: {', '.join(failed_api_updates[:10])}{'...' if len(failed_api_updates) > 10 else ''}")

    # Step 1.5: Update ticker extremes for successfully updated tickers
    print("\n🎯 Step 1.5: Updating ticker extremes (max/min prices)")
    print("-" * 50)

    failed_extremes_updates = []
    successful_extremes_updates = []

    if not successful_api_updates:
        print("   ℹ️  No successful API updates. Skipping extremes update.")
    else:
        print(f"   Processing {len(successful_api_updates)} ticker(s)")

        for i, ticker in enumerate(successful_api_updates, 1):
            print(f"[{i:3d}/{len(successful_api_updates)}] 🎯 Updating extremes for {ticker}")
            try:
                t0 = time.perf_counter()
                update_ticker_extremes(ticker)
                elapsed = time.perf_counter() - t0

                _add_profile_row("ticker_extremes", ticker, elapsed, ticker=ticker)
                successful_extremes_updates.append(ticker)
                print(f"                   ✅ Completed in {elapsed:.2f}s")

            except Exception as e:
                print(f"                   ❌ Error: {e}")
                connection.rollback()  # Rollback the failed transaction
                failed_extremes_updates.append(ticker)
                continue

        print(f"\n🎯 Ticker Extremes Summary:")
        print(f"   ✅ Successful: {len(successful_extremes_updates)}")
        print(f"   ❌ Failed: {len(failed_extremes_updates)}")

        if failed_extremes_updates:
            print(f"   Failed tickers: {', '.join(failed_extremes_updates[:10])}{'...' if len(failed_extremes_updates) > 10 else ''}")

    # Step 2: Create historical trendlines for 2024-01-01 (ONLY for new tickers)
    print("\n📊 Step 2: Creating historical trendlines for 2024-01-01 (new tickers only)")
    print("-" * 50)

    print("\n⏩ Step 2: SKIPPED (running only Step 1.5 and Step 3)")

    analysis_date = "2024-01-01"

    failed_upper_trendline_updates = []
    successful_upper_trendline_updates = []
    failed_under_trendline_updates = []
    successful_under_trendline_updates = []

    if not new_tickers:
        print("   ℹ️  No new tickers to process. Skipping Step 2.")
    else:
        print(f"   Processing {len(new_tickers)} new ticker(s)")

        # Step 2a: Create UPPER trendlines
        print(f"\n   📈 Step 2a: Creating UPPER (resistance) trendlines")
        for i, ticker in enumerate(new_tickers, 1):
            print(f"   [{i:3d}/{len(new_tickers)}] 📈 Creating upper trendline for {ticker}")
            try:
                t0 = time.perf_counter()
                find_and_update_upper_trendline_historical(ticker, analysis_date)
                elapsed = time.perf_counter() - t0

                _add_profile_row("historical_upper_trendlines", ticker, elapsed, ticker=ticker)
                successful_upper_trendline_updates.append(ticker)
                print(f"                      ✅ Completed in {elapsed:.2f}s")

            except Exception as e:
                print(f"                      ❌ Error: {e}")
                connection.rollback()  # Rollback the failed transaction
                failed_upper_trendline_updates.append(ticker)
                continue

        # Step 2b: Create LOWER trendlines
        print(f"\n   📉 Step 2b: Creating LOWER (support) trendlines")
        for i, ticker in enumerate(new_tickers, 1):
            print(f"   [{i:3d}/{len(new_tickers)}] 📉 Creating lower trendline for {ticker}")
            try:
                t0 = time.perf_counter()
                find_and_update_under_trendline_historical(ticker, analysis_date)
                elapsed = time.perf_counter() - t0

                _add_profile_row("historical_under_trendlines", ticker, elapsed, ticker=ticker)
                successful_under_trendline_updates.append(ticker)
                print(f"                      ✅ Completed in {elapsed:.2f}s")

            except Exception as e:
                print(f"                      ❌ Error: {e}")
                connection.rollback()  # Rollback the failed transaction
                failed_under_trendline_updates.append(ticker)
                continue

        print(f"\n📊 Historical Trendlines Summary:")
        print(f"   📈 Upper (resistance):")
        print(f"      ✅ Successful: {len(successful_upper_trendline_updates)}")
        print(f"      ❌ Failed: {len(failed_upper_trendline_updates)}")
        print(f"   📉 Lower (support):")
        print(f"      ✅ Successful: {len(successful_under_trendline_updates)}")
        print(f"      ❌ Failed: {len(failed_under_trendline_updates)}")

        if failed_upper_trendline_updates:
            print(f"   Failed upper tickers: {', '.join(failed_upper_trendline_updates[:10])}{'...' if len(failed_upper_trendline_updates) > 10 else ''}")
        if failed_under_trendline_updates:
            print(f"   Failed lower tickers: {', '.join(failed_under_trendline_updates[:10])}{'...' if len(failed_under_trendline_updates) > 10 else ''}")

    # Step 3: Update historical status for ALL tickers (both upper and lower)
    print("\n🔍 Step 3: Updating historical status (all tickers)")
    print("-" * 50)

    failed_upper_status_updates = []
    successful_upper_status_updates = []
    failed_under_status_updates = []
    successful_under_status_updates = []

    # Step 3a: Update UPPER status
    print(f"\n   📈 Step 3a: Updating UPPER (resistance) status")
    for i, ticker in enumerate(tickers, 1):
        print(f"   [{i:3d}/{len(tickers)}] 📈 Updating upper status for {ticker}")
        try:
            t0 = time.perf_counter()
            update_upper_status_historical(ticker)
            elapsed = time.perf_counter() - t0

            _add_profile_row("historical_upper_status", ticker, elapsed, ticker=ticker)
            successful_upper_status_updates.append(ticker)
            print(f"                    ✅ Completed in {elapsed:.2f}s")

        except Exception as e:
            print(f"                    ❌ Error: {e}")
            connection.rollback()  # Rollback the failed transaction
            failed_upper_status_updates.append(ticker)
            continue

    # Step 3b: Update LOWER status
    print(f"\n   📉 Step 3b: Updating LOWER (support) status")
    for i, ticker in enumerate(tickers, 1):
        print(f"   [{i:3d}/{len(tickers)}] 📉 Updating lower status for {ticker}")
        try:
            t0 = time.perf_counter()
            update_under_status_historical(ticker)
            elapsed = time.perf_counter() - t0

            _add_profile_row("historical_under_status", ticker, elapsed, ticker=ticker)
            successful_under_status_updates.append(ticker)
            print(f"                    ✅ Completed in {elapsed:.2f}s")

        except Exception as e:
            print(f"                    ❌ Error: {e}")
            connection.rollback()  # Rollback the failed transaction
            failed_under_status_updates.append(ticker)
            continue

    print(f"\n🔍 Historical Status Summary:")
    print(f"   📈 Upper (resistance):")
    print(f"      ✅ Successful: {len(successful_upper_status_updates)}")
    print(f"      ❌ Failed: {len(failed_upper_status_updates)}")
    print(f"   📉 Lower (support):")
    print(f"      ✅ Successful: {len(successful_under_status_updates)}")
    print(f"      ❌ Failed: {len(failed_under_status_updates)}")

    if failed_upper_status_updates:
        print(f"   Failed upper tickers: {', '.join(failed_upper_status_updates[:10])}{'...' if len(failed_upper_status_updates) > 10 else ''}")
    if failed_under_status_updates:
        print(f"   Failed lower tickers: {', '.join(failed_under_status_updates[:10])}{'...' if len(failed_under_status_updates) > 10 else ''}")

    # Final Summary
    end_time = time.time()
    execution_time = end_time - start_time

    print("\n" + "=" * 60)
    print("🎯 PIPELINE COMPLETED")
    print("=" * 60)
    print(f"📊 Total tickers processed: {total_tickers}")
    # print(f"✅ API updates successful: {len(successful_api_updates)}")
    print(f"🎯 Extremes updated: {len(successful_extremes_updates)}")
    print(f"📈 Upper trendlines created: {len(successful_upper_trendline_updates)}")
    print(f"📉 Lower trendlines created: {len(successful_under_trendline_updates)}")
    print(f"📈 Upper status updates completed: {len(successful_upper_status_updates)}")
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
        dump_profile_csv("historical_pipeline_profile.csv")
        print(f"📝 Profiling data saved to historical_pipeline_profile.csv")
    except Exception as e:
        print(f"⚠️  Warning: Could not save profiling data: {e}")

    # Close database connection
    if connection:
        cursor.close()
        connection.close()
        print("🔐 Database connection closed")


if __name__ == "__main__":
   historical_analysis_pipeline()