import numpy as np
import psycopg2
import pandas as pd
from db import updateDBWithAPI, update_status, find_and_update_upper_trendline, \
    find_and_update_under_trendline, check_and_update_upper_trendline, update_daily_move
import time


db_config = {
    'dbname': 'stock_data',      # Name of your database
    'user': 'shimonyannay',          # Your PostgreSQL username
    'password': 'Apple2020', # Your PostgreSQL password
    'host': 'localhost',         # Hostname (localhost for local)
    'port': 5432                 # Default PostgreSQL port
}

connection = psycopg2.connect(**db_config)
cursor = connection.cursor()


def daily_update():
    """
    Update stock data for all tickers stored in the `tickers` table.
    """
    start_time = time.time()

    # Fetch all tickers from the `tickers` table
    cursor.execute("SELECT ticker FROM tickers;")
    rows = cursor.fetchall()

    # Extract tickers into a list
    tickers = [row[0] for row in rows]

    # Process each ticker
    for ticker in tickers:
        print(f"UPDATE {ticker}")
        try:
            updated_dates = updateDBWithAPI(ticker)
            update_status(ticker)
            if len(updated_dates) > 0:
                check_and_update_upper_trendline(ticker, updated_dates)
            update_daily_move(ticker)
            # find_and_update_upper_trendline(ticker)
            # find_and_update_under_trendline(ticker)
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            continue

    if connection:
        cursor.close()
        connection.close()

    end_time = time.time()
    execution_time = end_time - start_time

    # Print the execution time in MM:SS or HH:MM:SS format
    if execution_time < 60:
        # For times under 1 minute, print seconds
        print(f"Execution time: {execution_time:.2f} seconds")
    elif execution_time < 3600:  # For times less than 1 hour
        minutes = int(execution_time // 60)  # Whole minutes
        seconds = int(execution_time % 60)  # Remaining seconds
        print(f"Execution time: {minutes:02}:{seconds:02}")  # Format as MM:SS
    else:
        hours = int(execution_time // 3600)  # Whole hours
        minutes = int((execution_time % 3600) // 60)  # Remaining minutes
        seconds = int(execution_time % 60)  # Remaining seconds
        print(f"Execution time: {hours:02}:{minutes:02}:{seconds:02}")
