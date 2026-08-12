#!/usr/bin/env python3
"""
Script to truncate stock_prices table and reload all data with raw prices.

WARNING: This will delete ALL data in stock_prices table!
"""

import psycopg2
from dotenv import load_dotenv
import os
import subprocess
import sys

load_dotenv()

db_config = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}


def main():
    print("=" * 70)
    print("TRUNCATE AND RELOAD STOCK PRICES")
    print("=" * 70)

    # Connect to database
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()

    # Show current stats
    cursor.execute("SELECT COUNT(*) FROM stock_prices;")
    count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT ticker) FROM stock_prices;")
    ticker_count = cursor.fetchone()[0]

    print(f"\n📊 Current Data:")
    print(f"   Rows: {count:,}")
    print(f"   Tickers: {ticker_count}")

    # Confirm
    print("\n⚠️  WARNING: This will DELETE ALL data in stock_prices table!")
    response = input("\nType 'YES' to continue: ")

    if response != 'YES':
        print("❌ Aborted.")
        conn.close()
        sys.exit(0)

    # Truncate
    print("\n🗑️  Truncating stock_prices table...")
    cursor.execute("TRUNCATE TABLE stock_prices;")
    conn.commit()
    print("✅ Table truncated successfully!")

    # Verify
    cursor.execute("SELECT COUNT(*) FROM stock_prices;")
    count = cursor.fetchone()[0]
    print(f"📊 Current rows: {count}")

    conn.close()

    # Run preload_prices.py
    print("\n" + "=" * 70)
    print("🔄 Starting preload_prices.py to reload data...")
    print("=" * 70)

    try:
        subprocess.run([sys.executable, "preload_prices.py"], check=True)
        print("\n✅ Data reload completed!")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error running preload_prices.py: {e}")
        sys.exit(1)

    # Show final stats
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM stock_prices;")
    final_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT ticker) FROM stock_prices;")
    final_ticker_count = cursor.fetchone()[0]

    print("\n" + "=" * 70)
    print("FINAL STATS")
    print("=" * 70)
    print(f"   Rows: {final_count:,}")
    print(f"   Tickers: {final_ticker_count}")

    conn.close()
    print("\n🎉 Process completed successfully!")


if __name__ == "__main__":
    main()
