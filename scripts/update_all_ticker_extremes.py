import psycopg2
import time
from dotenv import load_dotenv
import os

# Import from our existing modules
from historical_analysis import update_ticker_extremes

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


def update_all_ticker_extremes():
    """
    Updates ticker_extremes for all tickers in the tickers table.
    """
    start_time = time.time()
    print("🎯 Starting Ticker Extremes Update for All Tickers")
    print("=" * 60)

    # Fetch all tickers from the tickers table
    cursor.execute("SELECT ticker FROM tickers;")
    rows = cursor.fetchall()
    tickers = [row[0] for row in rows]

    total_tickers = len(tickers)
    print(f"📊 Processing {total_tickers} tickers")
    print("-" * 60)

    failed_updates = []
    successful_updates = []

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:3d}/{total_tickers}] 🎯 Updating extremes for {ticker}")
        try:
            t0 = time.perf_counter()
            update_ticker_extremes(ticker)
            elapsed = time.perf_counter() - t0

            successful_updates.append(ticker)
            print(f"                   ✅ Completed in {elapsed:.2f}s")

        except Exception as e:
            print(f"                   ❌ Error: {e}")
            failed_updates.append(ticker)
            continue

    # Summary
    end_time = time.time()
    execution_time = end_time - start_time

    print("\n" + "=" * 60)
    print("🎯 UPDATE COMPLETED")
    print("=" * 60)
    print(f"📊 Total tickers: {total_tickers}")
    print(f"✅ Successful: {len(successful_updates)}")
    print(f"❌ Failed: {len(failed_updates)}")

    if failed_updates:
        print(f"\n❌ Failed tickers: {', '.join(failed_updates[:20])}{'...' if len(failed_updates) > 20 else ''}")

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

    # Close database connection
    if connection:
        cursor.close()
        connection.close()
        print("🔐 Database connection closed")


if __name__ == "__main__":
    update_all_ticker_extremes()
