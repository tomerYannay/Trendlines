import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

from tests import d_update_upper_status, d_check_and_update_upper_trendline, d_find_and_update_upper_trendline

# Load .env variables
load_dotenv()

# Database configuration
db_config = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

# Connect to the database
connection = psycopg2.connect(**db_config)
cursor = connection.cursor()


def run_upper_status_backtest(ticker, start_date, end_date):

    # 🔄 Clear all previous data from upper_status_demo
    # print("🧹 Deleting all rows from upper_status_demo...")
    # cursor.execute("DELETE FROM upper_status_demo;")
    # connection.commit()

    # Fetch trading dates in the desired range
    cursor.execute("""
        SELECT DISTINCT date
        FROM stock_prices_demo
        WHERE ticker = %s AND date >= %s AND date <= %s
        ORDER BY date;
    """, (ticker, start_date, end_date))
    dates = cursor.fetchall()

    if not dates:
        print("No trading dates found for the given range.")
        return

    d_find_and_update_upper_trendline(ticker, start_date)
    for (date,) in dates:
        date_str = date.strftime('%Y-%m-%d')
        print(f"\n📆 Running backtest for {ticker} on {date_str}")
        d_update_upper_status(ticker, date_str)
        d_check_and_update_upper_trendline(ticker, [date_str])


# Run it!
if __name__ == "__main__":
    try:
        tickers = ['MMM', 'AOS', 'ABT', 'ABBV', 'ACN','ADBE','AMD','AES','AFL','A','APD','ABNB','AKAM','ALB','ARE',
                   'ALGN','ALLE','LNT','ALL','GOOGL','MO','AMZN','AMCR','AEE','AEP','AXP','AIG',
                   'AMT','AWK','AMP','AME','AMGN','APH','ADI','ANSS','AON','APA',
                   'APO','AMAT','APTV','ACGL','ADM','ANET','AJG','AIZ','T',
                   'ATO','ADSK','ADP','AZO','AVB','AVY','AXON','BKR','BALL','BAC','BAX']

        for ticker in tickers:
            try:
                run_upper_status_backtest(ticker, '2010-01-08', '2025-03-01')
            except:
                continue
    finally:
        cursor.close()
        connection.close()
