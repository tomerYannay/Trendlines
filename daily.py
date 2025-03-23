import numpy as np
import psycopg2
import pandas as pd
from db import updateDBWithAPI, update_upper_status, find_and_update_upper_trendline, \
    find_and_update_under_trendline, check_and_update_upper_trendline, update_daily_move, update_under_status, \
    check_and_update_under_trendline, update_upper_portfolio, update_under_portfolio
import time
from dotenv import load_dotenv
import os

# Load environment variables from the .env file
load_dotenv()

# Get the database credentials from the environment variables
db_username = os.getenv('DB_USERNAME')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')

# Now you can use these variables to connect to the database

db_config = {
    'dbname': db_name,      # Name of your database
    'user': db_username,          # Your PostgreSQL username
    'password': db_password, # Your PostgreSQL password
    'host': db_host,         # Hostname (localhost for local)
    'port': db_port                 # Default PostgreSQL port
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
            # updated_dates = updateDBWithAPI(ticker)
            # update_upper_status(ticker)
            # update_under_status(ticker)
            # if len(updated_dates) > 0:
            #     check_and_update_upper_trendline(ticker, updated_dates)
            #     check_and_update_under_trendline(ticker, updated_dates)
            find_and_update_upper_trendline(ticker)
            find_and_update_under_trendline(ticker)
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            continue

    for ticker in tickers:
        update_daily_move(ticker)

    # update_upper_portfolio()
    # update_under_portfolio()

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