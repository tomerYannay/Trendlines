#!/usr/bin/env python3
"""
Test script for the ticker_extremes functionality.
This script will:
1. Create the ticker_extremes table if it doesn't exist
2. Test the update_ticker_extremes function with a single ticker
3. Verify the data was inserted correctly
"""

import sys
from historical_analysis import update_ticker_extremes, get_db_connection

def create_table():
    """Create the ticker_extremes table if it doesn't exist"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        print("Creating ticker_extremes table if it doesn't exist...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticker_extremes (
                ticker VARCHAR(10) PRIMARY KEY,
                max_price NUMERIC(10, 2) NOT NULL,
                min_price NUMERIC(10, 2) NOT NULL,
                max_date DATE NOT NULL,
                min_date DATE NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticker_extremes_ticker
            ON ticker_extremes(ticker);
        """)

        connection.commit()
        print("✅ Table created successfully or already exists")

    except Exception as e:
        print(f"❌ Error creating table: {e}")
        connection.rollback()
    finally:
        cursor.close()
        connection.close()

def test_single_ticker(ticker):
    """Test the update_ticker_extremes function with a single ticker"""
    print(f"\n{'='*60}")
    print(f"Testing update_ticker_extremes for: {ticker}")
    print('='*60)

    try:
        update_ticker_extremes(ticker)

        # Verify the data was inserted
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT ticker, max_price, min_price, max_date, min_date, last_updated
            FROM ticker_extremes
            WHERE ticker = %s;
        """, (ticker,))

        result = cursor.fetchone()

        if result:
            print(f"\n✅ Data successfully inserted/updated for {ticker}:")
            print(f"   Max Price: ${result[1]} on {result[3]}")
            print(f"   Min Price: ${result[2]} on {result[4]}")
            print(f"   Last Updated: {result[5]}")
        else:
            print(f"\n⚠️ No data found for {ticker} in ticker_extremes table")

        cursor.close()
        connection.close()

    except Exception as e:
        print(f"\n❌ Error testing {ticker}: {e}")

def main():
    """Main test function"""
    print("="*60)
    print("TICKER EXTREMES TEST SCRIPT")
    print("="*60)

    # Step 1: Create table
    create_table()

    # Step 2: Get a sample ticker from the database
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT ticker
            FROM tickers
            LIMIT 1;
        """)
        result = cursor.fetchone()

        if result:
            sample_ticker = result[0]
            test_single_ticker(sample_ticker)
        else:
            print("\n⚠️ No tickers found in tickers table. Cannot run test.")

    except Exception as e:
        print(f"\n❌ Error fetching sample ticker: {e}")
    finally:
        cursor.close()
        connection.close()

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
