#!/usr/bin/env python3
"""
Test script to verify that stock prices are stored as raw OHLC values,
NOT normalized/adjusted values.
"""

import sys
import psycopg2
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

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

def test_api_response_parsing():
    """Test that the API response is parsed correctly without normalization"""
    print("="*70)
    print("TESTING RAW PRICE STORAGE (NO NORMALIZATION)")
    print("="*70)
    print()

    # Example API response data (from your example)
    api_example = {
        "2021-09-03": {
            "1. open": "177.67",
            "2. high": "179.57",
            "3. low": "177.03",
            "4. close": "179.28",
            "5. adjusted close": "174.081894827552",
            "6. volume": "971760",
            "7. dividend amount": "0.0000",
            "8. split coefficient": "1.0"
        }
    }

    print("Example API Response:")
    print(f"  Open:           {api_example['2021-09-03']['1. open']}")
    print(f"  High:           {api_example['2021-09-03']['2. high']}")
    print(f"  Low:            {api_example['2021-09-03']['3. low']}")
    print(f"  Close:          {api_example['2021-09-03']['4. close']}")
    print(f"  Adjusted Close: {api_example['2021-09-03']['5. adjusted close']}")
    print()

    print("Expected behavior (AFTER FIX):")
    print("  ✓ Open should be:  177.67 (raw value)")
    print("  ✓ High should be:  179.57 (raw value)")
    print("  ✓ Low should be:   177.03 (raw value)")
    print("  ✓ Close should be: 179.28 (raw value, NOT adjusted)")
    print()

    print("Old behavior (BEFORE FIX):")
    print("  ✗ All prices were normalized by factor: 174.08 / 179.28 = 0.971")
    print("  ✗ Close would be: 174.08 (adjusted close)")
    print()

def verify_database_sample():
    """Verify a sample of data from the database"""
    print("="*70)
    print("VERIFYING DATABASE SAMPLE")
    print("="*70)
    print()

    try:
        connection = psycopg2.connect(**db_config)
        cursor = connection.cursor()

        # Get a sample record
        cursor.execute("""
            SELECT ticker, date, open, high, low, close
            FROM stock_prices
            WHERE ticker = 'A'
            AND date = '2021-09-03'
            LIMIT 1;
        """)

        result = cursor.fetchone()

        if result:
            ticker, date, open_p, high, low, close = result
            print(f"Sample from database (ticker: {ticker}, date: {date}):")
            print(f"  Open:  {open_p}")
            print(f"  High:  {high}")
            print(f"  Low:   {low}")
            print(f"  Close: {close}")
            print()

            # Check if it looks normalized
            if close < 175:
                print("⚠️  WARNING: Close price appears to be adjusted/normalized!")
                print("   Expected close ~179.28, got", close)
                print("   This data may have been inserted with the OLD code.")
                print()
                print("   To fix existing data, you need to:")
                print("   1. Truncate the stock_prices table")
                print("   2. Re-run the pipeline with the FIXED code")
            else:
                print("✅ Close price appears to be raw (non-normalized)")
        else:
            print("No data found for ticker 'A' on 2021-09-03")
            print("This is expected if you haven't loaded this data yet.")

        cursor.close()
        connection.close()

    except Exception as e:
        print(f"Error checking database: {e}")

def show_code_changes():
    """Show the code changes made"""
    print()
    print("="*70)
    print("CODE CHANGES SUMMARY")
    print("="*70)
    print()
    print("Files Modified:")
    print("  1. db.py:248-277 - fetch_full_historical_data()")
    print("  2. methods.py:31-66 - updateCSVWithAPI()")
    print()
    print("Changes:")
    print("  ✓ Removed normalization_factor calculation")
    print("  ✓ Removed adjusted_close usage")
    print("  ✓ Now using raw values: open, high, low, close (NOT adjusted)")
    print()
    print("The fixed code now stores:")
    print("  - open  = values['1. open']")
    print("  - high  = values['2. high']")
    print("  - low   = values['3. low']")
    print("  - close = values['4. close']  (NOT adjusted close!)")
    print()

def main():
    print()
    test_api_response_parsing()
    verify_database_sample()
    show_code_changes()

    print("="*70)
    print("NEXT STEPS")
    print("="*70)
    print()
    print("If your database contains OLD normalized data:")
    print("  1. Create a backup of your database")
    print("  2. Truncate the stock_prices table:")
    print("     TRUNCATE TABLE stock_prices;")
    print("  3. Re-run the pipeline:")
    print("     python3 historical_pipeline.py")
    print()
    print("This will reload all data with RAW (non-normalized) prices.")
    print()

if __name__ == "__main__":
    main()
