#!/usr/bin/env python3
"""
Run historical analysis for all tickers starting from 2024-01-01
"""

import time
from historical_analysis import (
    get_db_connection,
    populate_historical_trendlines_for_date_range,
    update_upper_status_historical,
    PROFILE_ROWS
)
import pandas as pd
from psycopg2.extras import DictCursor

def get_all_tickers():
    """Get all tickers from the database"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute('SELECT DISTINCT ticker FROM tickers_russell ORDER BY ticker;')
    tickers = [row['ticker'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    return tickers

def run_historical_analysis_from_date(start_date='2024-01-01'):
    """
    Run complete historical analysis for all tickers starting from specified date
    """
    print(f"Starting historical analysis from {start_date}")
    
    # Get all tickers
    tickers = get_all_tickers()
    print(f"Found {len(tickers)} tickers to process")
    
    # Get end date (latest available data)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(date) FROM stock_prices;")
    end_date = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    print(f"Processing date range: {start_date} to {end_date}")
    
    start_time = time.time()
    processed_count = 0
    
    for i, ticker in enumerate(tickers, 1):
        try:
            print(f"[{i}/{len(tickers)}] Processing {ticker}...")
            
            # Step 1: Populate historical trendlines for the date range
            print(f"  - Populating historical trendlines...")
            populate_historical_trendlines_for_date_range(ticker, start_date, end_date)
            
            # Step 2: Update historical status using the calculated trendlines
            print(f"  - Updating historical status...")
            update_upper_status_historical(ticker)
            
            processed_count += 1
            
            # Progress update every 50 tickers
            if i % 50 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / processed_count
                remaining = len(tickers) - processed_count
                estimated_remaining = remaining * avg_time
                
                print(f"\nProgress: {i}/{len(tickers)} ({i/len(tickers)*100:.1f}%)")
                print(f"Elapsed: {elapsed/60:.1f} minutes")
                print(f"Estimated remaining: {estimated_remaining/60:.1f} minutes")
                print(f"Average time per ticker: {avg_time:.1f} seconds\n")
            
        except Exception as e:
            print(f"ERROR processing {ticker}: {e}")
            continue
    
    total_time = time.time() - start_time
    print(f"\nCompleted historical analysis!")
    print(f"Total time: {total_time/60:.1f} minutes")
    print(f"Processed {processed_count}/{len(tickers)} tickers")
    
    # Save profiling data
    if PROFILE_ROWS:
        profile_df = pd.DataFrame(PROFILE_ROWS)
        profile_df.to_csv('historical_analysis_profile.csv', index=False)
        print(f"Saved profiling data to historical_analysis_profile.csv")

if __name__ == "__main__":
    run_historical_analysis_from_date('2024-01-01')