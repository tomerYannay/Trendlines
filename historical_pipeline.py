import numpy as np
import psycopg2
import pandas as pd
import time
from dotenv import load_dotenv
import os

# Import from our existing modules
from db import updateDBWithAPI, _add_profile_row, dump_profile_csv
from historical_analysis import (
    find_and_update_upper_trendline_historical, 
    update_upper_status_historical
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
    1. Updates all tickers with latest API data
    2. Creates historical trendlines for 2024-01-01
    3. Updates historical upper status for all tickers
    """
    start_time = time.time()
    print("🚀 Starting Historical Analysis Pipeline")
    print("=" * 60)

    # Fetch all tickers from the Russell table
    cursor.execute("SELECT ticker FROM tickers_russell;")
    rows = cursor.fetchall()
    tickers = [row[0] for row in rows]
    
    total_tickers = len(tickers)
    print(f"📊 Processing {total_tickers} tickers")
    
    # # Step 1: Update all tickers with latest API data
    # print("\n🔄 Step 1: Updating all tickers with latest API data")
    # print("-" * 50)
    
    # failed_api_updates = []
    # successful_api_updates = []
    
    # for i, ticker in enumerate(tickers, 1):
    #     print(f"[{i:3d}/{total_tickers}] 🔄 Updating API data for {ticker}")
    #     try:
    #         t0 = time.perf_counter()
    #         updated_dates = updateDBWithAPI(ticker)
    #         elapsed = time.perf_counter() - t0
            
    #         _add_profile_row("api_update", ticker, elapsed, ticker=ticker)
    #         successful_api_updates.append(ticker)
            
    #         if updated_dates:
    #             print(f"              ✅ Updated {len(updated_dates)} new dates")
    #         else:
    #             print(f"              ℹ️  No new data")
                
    #     except Exception as e:
    #         print(f"              ❌ Error: {e}")
    #         failed_api_updates.append(ticker)
    #         continue
    
    # print(f"\n📈 API Update Summary:")
    # print(f"   ✅ Successful: {len(successful_api_updates)}")
    # print(f"   ❌ Failed: {len(failed_api_updates)}")
    
    # if failed_api_updates:
    #     print(f"   Failed tickers: {', '.join(failed_api_updates[:10])}{'...' if len(failed_api_updates) > 10 else ''}")

    # # Step 2: Create historical trendlines for 2024-01-01
    # print("\n📊 Step 2: Creating historical trendlines for 2024-01-01")
    # print("-" * 50)
    
    # analysis_date = "2024-01-01"
    
    # failed_trendline_updates = []
    # successful_trendline_updates = []
    
    # for i, ticker in enumerate(tickers, 1):
    #     print(f"[{i:3d}/{len(tickers)}] 📈 Creating historical trendline for {ticker}")
    #     try:
    #         t0 = time.perf_counter()
    #         find_and_update_upper_trendline_historical(ticker, analysis_date)
    #         elapsed = time.perf_counter() - t0
            
    #         _add_profile_row("historical_trendlines", ticker, elapsed, ticker=ticker)
    #         successful_trendline_updates.append(ticker)
    #         print(f"                   ✅ Completed in {elapsed:.2f}s")
            
    #     except Exception as e:
    #         print(f"                   ❌ Error: {e}")
    #         failed_trendline_updates.append(ticker)
    #         continue
    
    # print(f"\n📊 Historical Trendlines Summary:")
    # print(f"   ✅ Successful: {len(successful_trendline_updates)}")
    # print(f"   ❌ Failed: {len(failed_trendline_updates)}")
    
    # if failed_trendline_updates:
    #     print(f"   Failed tickers: {', '.join(failed_trendline_updates[:10])}{'...' if len(failed_trendline_updates) > 10 else ''}")

    # Step 3: Update historical upper status for all tickers
    print("\n🔍 Step 3: Updating historical upper status")
    print("-" * 50)
    
    failed_status_updates = []
    successful_status_updates = []
    
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:3d}/{len(tickers)}] 🔍 Updating historical status for {ticker}")
        try:
            t0 = time.perf_counter()
            update_upper_status_historical(ticker)
            elapsed = time.perf_counter() - t0
            
            _add_profile_row("historical_status", ticker, elapsed, ticker=ticker)
            successful_status_updates.append(ticker)
            print(f"                 ✅ Completed in {elapsed:.2f}s")
            
        except Exception as e:
            print(f"                 ❌ Error: {e}")
            failed_status_updates.append(ticker)
            continue

    print(f"\n🔍 Historical Status Summary:")
    print(f"   ✅ Successful: {len(successful_status_updates)}")
    print(f"   ❌ Failed: {len(failed_status_updates)}")
    
    if failed_status_updates:
        print(f"   Failed tickers: {', '.join(failed_status_updates[:10])}{'...' if len(failed_status_updates) > 10 else ''}")

    # Final Summary
    end_time = time.time()
    execution_time = end_time - start_time
    
    print("\n" + "=" * 60)
    print("🎯 PIPELINE COMPLETED")
    print("=" * 60)
    print(f"📊 Total tickers processed: {total_tickers}")
    print(f"✅ API updates successful: {len(successful_api_updates)}")
    print(f"📈 Trendlines created: {len(successful_trendline_updates)}")
    print(f"🔍 Status updates completed: {len(successful_status_updates)}")
    
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