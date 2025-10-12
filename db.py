import time
import numpy as np
import requests
from psycopg2.extras import execute_values
import pandas as pd
import psycopg2
from dotenv import load_dotenv
import os
from psycopg2.extras import DictCursor

# Load environment variables from the .env file
load_dotenv()

# Get the database credentials from the environment variables
db_username = os.getenv('DB_USERNAME')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')

db_config = {
    'dbname': db_name,      # Name of your database
    'user': db_username,          # Your PostgreSQL username
    'password': db_password, # Your PostgreSQL password
    'host': db_host,         # Hostname (localhost for local)
    'port': db_port                 # Default PostgreSQL port
}

# Connect to the database
connection = psycopg2.connect(**db_config)
cursor = connection.cursor()


from datetime import datetime

import time
import csv
from functools import wraps
from contextlib import contextmanager
from datetime import datetime

# === Simple profiler ===
PROFILE_ENABLED = True  # תוכל לכבות/להדליק לפי צורך
PROFILE_ROWS = []       # כאן נצבור תוצאות

def _add_profile_row(scope, name, elapsed, ticker=None, extra=None):
    PROFILE_ROWS.append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "scope": scope,             # function / block / api / ticker
        "name": name,               # שם הפונקציה/הבלוק/ה־API
        "ticker": ticker or "",
        "elapsed_sec": round(elapsed, 4),
        "extra": extra or ""
    })

def dump_profile_csv(path="profile_times.csv"):
    if not PROFILE_ROWS:
        return
    fieldnames = ["ts","scope","name","ticker","elapsed_sec","extra"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(PROFILE_ROWS)
    print(f"📝 Profile written to {path}")

def timed(name=None, scope="function"):
    """
    דקורטור למדידת פונקציות. שימוש: @timed() או @timed("updateDBWithAPI")
    """
    def deco(func):
        label = name or func.__name__
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not PROFILE_ENABLED:
                return func(*args, **kwargs)
            t0 = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                t1 = time.perf_counter()
                # נסה לחלץ טיקר אם זו הפרמטר הראשון (מקובל אצלך)
                ticker = None
                if args and isinstance(args[0], str) and args[0].isupper():
                    ticker = args[0]
                _add_profile_row(scope, label, t1 - t0, ticker=ticker)
        return wrapper
    return deco

@contextmanager
def time_block(name, scope="block", ticker=None, extra=None):
    """
    לקוד נקודתי (SQL/requests). שימוש:
    with time_block("SELECT max(date)", scope="sql", ticker=ticker):
        cursor.execute(...)
    """
    if not PROFILE_ENABLED:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        t1 = time.perf_counter()
        _add_profile_row(scope, name, t1 - t0, ticker=ticker, extra=extra)


def fetch_ti_for_date(url, key, subkey, ins_date):
    time.sleep(1)
    resp = http_get_timed(url, scope="api", name=subkey, ticker=None)
    if resp.status_code != 200:
        return None
    j = resp.json()
    series = j.get(key)
    if not series:
        return None

    try:
        target = datetime.strptime(ins_date, "%Y-%m-%d")
    except:
        return None

    best_val, best_d = None, None
    for k, v in series.items():
        try:
            d = datetime.strptime(k, "%Y-%m-%d")
            if d <= target and subkey in v and v[subkey] not in (None, ""):
                if best_d is None or d > best_d:
                    best_d, best_val = d, v[subkey]
        except:
            continue
    return best_val

def http_get_timed(url, scope="api", name=None, ticker=None):
    if PROFILE_ENABLED:
        t0 = time.perf_counter()
    resp = requests.get(url)
    if PROFILE_ENABLED:
        t1 = time.perf_counter()
        _add_profile_row(scope, name or url.split("function=")[-1][:40], t1 - t0, ticker=ticker, extra=url)
    return resp

@timed()
def fetch_latest_global_quote(symbol, prem_key='8LLD101ZZ48BBVC8'):
    """
    Fetch only the latest day's OHLCV using Alpha Vantage GLOBAL_QUOTE.
    """
    url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={prem_key}'
    # 🔥 no sleep
    r = http_get_timed(url, scope="api", name="GLOBAL_QUOTE", ticker=symbol)
    if r.status_code != 200:
        raise ConnectionError(f"Failed to fetch GLOBAL_QUOTE for {symbol}: {r.status_code}")

    data = r.json()
    if "Global Quote" not in data or not data["Global Quote"]:
        raise ValueError(f"Invalid GLOBAL_QUOTE response for {symbol}: {data}")

    g = data["Global Quote"]
    latest_date = g.get("07. latest trading day")
    if not latest_date:
        raise ValueError(f"No 'latest trading day' in GLOBAL_QUOTE for {symbol}: {data}")

    return {
        "date": latest_date,
        "open": float(g["02. open"]),
        "high": float(g["03. high"]),
        "low": float(g["04. low"]),
        "close": float(g["05. price"]),
        "volume": int(g["06. volume"]) if g.get("06. volume") not in (None, "") else None
    }



@timed()
def fetchDailyJson(symbol, prem_key='8LLD101ZZ48BBVC8'):
    """
    Fetch daily stock data for the given symbol using Alpha Vantage API.
    """
    api_url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize=compact&apikey={prem_key}'
    time.sleep(1)  # To prevent exceeding API rate limits
    response = requests.get(api_url)
    if response.status_code == 200:
        data = response.json()
        if "Time Series (Daily)" in data:
            return data['Time Series (Daily)']
        else:
            raise ValueError(f"Error in API response for {symbol}: {data}")
    else:
        raise ConnectionError(f"Failed to fetch data for {symbol}: {response.status_code}")

@timed()
def add_close_high_low_open(symbol, prem_key='8LLD101ZZ48BBVC8'):
    """
    Insert ONLY the latest daily bar using GLOBAL_QUOTE.
    No adjusted normalization is applied here (raw market OHLCV).
    """
    latest = fetch_latest_global_quote(symbol, prem_key=prem_key)
    date = latest["date"]

    # בדוק אם היום כבר קיים
    cursor.execute(
        "SELECT 1 FROM stock_prices WHERE ticker = %s AND date = %s;",
        (symbol, date)
    )
    exists = cursor.fetchone()

    if exists:
        print(f"{symbol}: latest date {date} already exists. No insert.")
        return

    vol = latest["volume"] if latest["volume"] is not None else 0  # <-- הוסף שורה זו

    row = (
        symbol, date, latest["open"], latest["high"], latest["low"], latest["close"], vol
    )

    execute_values(
        cursor,
        """
        INSERT INTO stock_prices (ticker, date, open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (ticker, date) DO NOTHING;
        """,
        [row]
    )
    connection.commit()
    print(f"Inserted latest day for {symbol}: {date}")


@timed()
def updateDBWithAPI(symbol, prem_key='8LLD101ZZ48BBVC8'):
    """
    Fast path: use GLOBAL_QUOTE to insert only the latest day.
    No indicators are fetched (for speed testing).
    """
    cursor.execute("SELECT MAX(date) FROM stock_prices WHERE ticker = %s;", (symbol,))
    latest_date_in_db = cursor.fetchone()[0]  # date or None

    try:
        # No sleep here
        latest = fetch_latest_global_quote(symbol, prem_key=prem_key)
    except Exception as e:
        print(f"GLOBAL_QUOTE failed for {symbol}: {e}")
        return []

    inserted_dates = []
    if latest:
        latest_date = latest["date"]
        if (latest_date_in_db is None) or (latest_date > latest_date_in_db.strftime('%Y-%m-%d')):
            vol = latest["volume"] if latest["volume"] is not None else 0
            execute_values(
                cursor,
                """
                INSERT INTO stock_prices (ticker, date, open, high, low, close, volume)
                VALUES %s
                ON CONFLICT (ticker, date) DO NOTHING;
                """,
                [(symbol, latest_date, latest["open"], latest["high"], latest["low"], latest["close"], vol)]
            )
            connection.commit()
            inserted_dates.append(latest_date)
            print(f"Inserted latest day for {symbol}: {latest_date}")
        else:
            print(f"{symbol}: DB already up-to-date through {latest_date_in_db}.")
    else:
        print(f"{symbol}: Skipping fast insert (GLOBAL_QUOTE unavailable).")

    return inserted_dates



@timed()
def update_upper_status(stock):
    """
    Update the new columns in the stock_prices table for a given stock
    """

    # Fetch trendline data from upper_trendlines
    cursor.execute("""
        SELECT date1, date2, slope
        FROM upper_trendlines
        WHERE ticker = %s;
    """, (stock,))
    trendline_data = cursor.fetchone()

    if not trendline_data:
        raise ValueError(f"No trendline data found for {stock}")

    date1, date2, slope = trendline_data

    # Fetch stock prices
    cursor.execute("""
        SELECT date, high, close
        FROM stock_prices
        WHERE ticker = %s
        ORDER BY date;
    """, (stock,))
    rows = cursor.fetchall()

    data = pd.DataFrame(rows, columns=['date', 'high', 'close'])
    data['high'] = data['high'].astype(float)
    data['close'] = data['close'].astype(float)

    # Extract unique trading dates and sort them
    trading_days = sorted(data['date'].unique())
    # Create a mapping of trading days to their indices
    trading_days_map = {day: idx for idx, day in enumerate(trading_days)}

    # Locate indices for date1 and date2
    index1 = trading_days_map[date1]
    index2 = trading_days_map[date2]

    # Calculate the required values
    data['trendline'] = calculate_upper_trendline(data, date1, date2)
    data['distance'] = ((data['trendline'].astype(float) - data['close']) / data['close']) * 100
    data['breakthrough'] = data['close'] > data['trendline']
    # Calculate durations in trading days
    data['duration_from_date1'] = data['date'].apply(lambda x: trading_days_map[x] - index1)
    data['duration_from_date2'] = data['date'].apply(lambda x: trading_days_map[x] - index2)
    data['sequence'] = calculate_sequence(data['breakthrough'])

    # Add a column for `update_trendline` based on the conditions
    data['previous_breakthrough'] = data['breakthrough'].shift(1, fill_value=False)
    data['update_trendline'] = (
            (data['sequence'] > 50) |
            ((data['distance'] > 0) & (data['previous_breakthrough'])) |
            (data['distance'] < -20)
    )

    # Drop temporary column
    data.drop(columns=['previous_breakthrough'], inplace=True)

    # Fetch existing entries in the under_status table for the given ticker
    cursor.execute("""
        SELECT date
        FROM upper_status
        WHERE ticker = %s;
    """, (stock,))
    existing_dates = {row[0] for row in cursor.fetchall()}

    # Fetch last update_all_lines date
    cursor.execute("""
        SELECT MAX(update_all_lines)
        FROM upper_status
        WHERE ticker = %s AND update_all_lines IS NOT NULL;
    """, (stock,))
    last_update_date = cursor.fetchone()[0]

    called_update_all = False
    # Insert rows for missing dates
    for _, row in data.iterrows():
        if row['date'] not in existing_dates:
            should_update = False

            if row['distance'] > 30:
                if last_update_date is None or (row['date'] - last_update_date).days >= 30:
                    should_update = True
                    last_update_date = row['date']  # Update reference for future rows

                    # Call update_all_upper_trendlines once
                    if not called_update_all:
                        update_all_upper_trendlines(stock)
                        called_update_all = True

            update_all_lines_date = row['date'] if should_update else None

            cursor.execute("""
                INSERT INTO upper_status (ticker, date, trendline, distance, breakthrough, duration_from_date1, 
                duration_from_date2, sequence, update_trendline, update_all_lines)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                stock, row['date'], row['trendline'], row['distance'], row['breakthrough'],
                row['duration_from_date1'], row['duration_from_date2'], row['sequence'], row['update_trendline'], update_all_lines_date
            ))

    connection.commit()
    print(f"Updated upper_status for {stock}")

@timed()
def calculate_upper_trendline(data, date1, date2):
    """
    Calculate trendline prices using logarithmic scale.
    This method follows the same logic as your earlier implementation but is made reusable.
    """

    trading_days = sorted(data['date'].unique())
    try:
        index1 = trading_days.index(date1)
        index2 = trading_days.index(date2)
    except:
        # # Locate indices for date1 and date2
        date1 = pd.Timestamp(date1)
        date2 = pd.Timestamp(date2)
        index1 = trading_days.index(date1)
        index2 = trading_days.index(date2)

    # Get high prices for date1 and date2
    price1 = float(data.loc[data['date'] == date1, 'high'].values[0])
    price2 = float(data.loc[data['date'] == date2, 'high'].values[0])

    # Calculate log prices and slope in logarithmic scale
    log_price1 = np.log(price1)
    log_price2 = np.log(price2)
    log_slope = (log_price2 - log_price1) / (index2 - index1)

    # Calculate trendline prices
    trendline_prices = []
    for i, current_date in enumerate(data['date']):
        current_index = trading_days.index(current_date)
        additional_trading_days = current_index - index2
        log_trend_price = log_price2 + log_slope * additional_trading_days
        trend_price = np.exp(log_trend_price)
        trendline_prices.append(round(trend_price, 2))

    return trendline_prices

@timed()
def update_under_status(stock):
    """
    Update the new columns in the stock_prices table for a given stock
    """

    # Fetch trendline data from stock_trendlines
    cursor.execute("""
        SELECT date1, date2, slope
        FROM under_trendlines
        WHERE ticker = %s;
    """, (stock,))
    trendline_data = cursor.fetchone()

    if not trendline_data:
        raise ValueError(f"No trendline data found for {stock}")

    date1, date2, slope = trendline_data

    # Fetch stock prices
    cursor.execute("""
        SELECT date, low, close
        FROM stock_prices
        WHERE ticker = %s
        ORDER BY date;
    """, (stock,))
    rows = cursor.fetchall()

    data = pd.DataFrame(rows, columns=['date', 'low', 'close'])
    data['low'] = data['low'].astype(float)
    data['close'] = data['close'].astype(float)

    # Extract unique trading dates and sort them
    trading_days = sorted(data['date'].unique())
    # Create a mapping of trading days to their indices
    trading_days_map = {day: idx for idx, day in enumerate(trading_days)}

    # Locate indices for date1 and date2
    index1 = trading_days_map[date1]
    index2 = trading_days_map[date2]

    # Calculate the required values
    data['trendline'] = calculate_under_trendline(data, date1, date2)
    data['distance'] = ((data['trendline'].astype(float) - data['close']) / data['close']) * 100
    data['breakthrough'] = data['close'] < data['trendline']
    # Calculate durations in trading days
    data['duration_from_date1'] = data['date'].apply(lambda x: trading_days_map[x] - index1)
    data['duration_from_date2'] = data['date'].apply(lambda x: trading_days_map[x] - index2)
    data['sequence'] = calculate_sequence(data['breakthrough'])

    # Add a column for `update_trendline` based on the conditions
    data['previous_breakthrough'] = data['breakthrough'].shift(1, fill_value=False)
    data['update_trendline'] = (
            (data['sequence'] > 50) |
            ((data['distance'] > 0) & (data['previous_breakthrough'])) |
            (data['distance'] > 20)
    )

    # Drop temporary column
    data.drop(columns=['previous_breakthrough'], inplace=True)

    # Fetch existing entries in the under_status table for the given ticker
    cursor.execute("""
        SELECT date
        FROM under_status
        WHERE ticker = %s;
    """, (stock,))
    existing_dates = {row[0] for row in cursor.fetchall()}

    # Insert rows for missing dates
    for _, row in data.iterrows():
        if row['date'] not in existing_dates:
            cursor.execute("""
                INSERT INTO under_status (ticker, date, trendline, distance, breakthrough, duration_from_date1, duration_from_date2, sequence, update_trendline)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                stock, row['date'], row['trendline'], row['distance'], row['breakthrough'],
                row['duration_from_date1'], row['duration_from_date2'], row['sequence'], row['update_trendline']
            ))

    # Update the table
    # for _, row in data.iterrows():
    #     cursor.execute("""
    #         UPDATE under_status
    #         SET trendline = %s,
    #             distance = %s,
    #             breakthrough = %s,
    #             duration_from_date1 = %s,
    #             duration_from_date2 = %s,
    #             sequence = %s,
    #             update_trendline = %s
    #         WHERE ticker = %s AND date = %s;
    #     """, (
    #         row['trendline'], row['distance'], row['breakthrough'],
    #         row['duration_from_date1'], row['duration_from_date2'],
    #         row['sequence'], row['update_trendline'], stock, row['date']
    #     ))

    connection.commit()
    print(f"Updated under_status for {stock}")

@timed()
def calculate_under_trendline(data, date1, date2):
    """
    Calculate trendline prices using logarithmic scale.
    This method follows the same logic as your earlier implementation but is made reusable.
    """
    # Locate indices for date1 and date2
    trading_days = sorted(data['date'].unique())
    index1 = trading_days.index(date1)
    index2 = trading_days.index(date2)

    # Get high prices for date1 and date2
    price1 = float(data.loc[data['date'] == date1, 'low'].values[0])
    price2 = float(data.loc[data['date'] == date2, 'low'].values[0])

    # Calculate log prices and slope in logarithmic scale
    log_price1 = np.log(price1)
    log_price2 = np.log(price2)
    log_slope = (log_price2 - log_price1) / (index2 - index1)

    # Calculate trendline prices
    trendline_prices = []
    for i, current_date in enumerate(data['date']):
        current_index = trading_days.index(current_date)
        additional_trading_days = current_index - index2
        log_trend_price = log_price2 + log_slope * additional_trading_days
        trend_price = np.exp(log_trend_price)
        trendline_prices.append(round(trend_price, 2))

    return trendline_prices

@timed()
def calculate_sequence(breakthrough_series):
    """Calculate sequence of TRUE values in breakthrough column."""
    sequence = []
    count = 0
    for value in breakthrough_series:
        if value:
            count += 1
        else:
            count = 0
        sequence.append(count)
    return sequence

@timed()
def find_and_update_upper_trendline(stock):
    """
    Find the highest price and validate the trendline for a given stock.
    Update the upper_trendlines table with new trendline data, including date_diff and index2.
    """

    # Fetch stock prices from the database
    cursor.execute("""
        SELECT date, high
        FROM stock_prices
        WHERE ticker = %s
        ORDER BY date;
    """, (stock,))
    rows = cursor.fetchall()

    if not rows:
        print(f"No data found for {stock}.")
        return

    # Convert the data into a DataFrame
    df = pd.DataFrame(rows, columns=['time', 'high'])
    df['time'] = pd.to_datetime(df['time'])
    df['high'] = df['high'].astype(float)

    # Extract unique trading dates and sort them
    trading_days = sorted(df['time'].unique())

    # Find the highest price and its date
    highest_row = df.loc[df['high'].idxmax()]
    date1 = highest_row['time']
    price1 = highest_row['high']

    # Initialize variables for the second point
    largest_negative_slope = float('-inf')
    best_date2 = None

    # Sort rows by 'high' in descending order for faster iteration
    sorted_df = df[df['time'] > date1].sort_values(by='high', ascending=False)

    # Iterate through sorted rows
    for index, row in sorted_df.iterrows():
        date2 = row['time']
        price2 = row['high']

        # Check if the high price of date2 equals the high price of date1
        if price2 == price1:
            slope = 0
            index1 = trading_days.index(date1)
            index2 = trading_days.index(date2)
            date_diff = index2 - index1

            # ⬅️ Fix here: use actual date2 and slope = 0
            cursor.execute("""
                INSERT INTO upper_trendlines (ticker, date1, date2, slope, date_diff, index2)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE
                SET date1 = EXCLUDED.date1,
                    date2 = EXCLUDED.date2,
                    slope = EXCLUDED.slope,
                    date_diff = EXCLUDED.date_diff,
                    index2 = EXCLUDED.index2;
            """, (stock, date1, date2, slope, date_diff, index2))
            connection.commit()

            print(
                f"Updated upper_trendlines for {stock}: Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")
            return

        # Calculate the number of trading days between date1 and date2
        index1 = trading_days.index(date1)
        index2 = trading_days.index(date2)
        date_diff = index2 - index1
        if date_diff == 0:
            continue  # Avoid division by zero

        # Calculate the slope in log scale
        log_price1 = np.log(price1)
        log_price2 = np.log(price2)
        slope = (log_price2 - log_price1) / date_diff

        # If valid and the slope is the largest negative slope, update the best point
        if slope > largest_negative_slope:
            largest_negative_slope = slope
            best_date2 = date2

    largest_negative_slope = float(largest_negative_slope)

    # Update the upper_trendlines table if a valid trendline is found
    if best_date2:
        index1 = trading_days.index(date1)
        index2 = trading_days.index(best_date2)
        date_diff = index2 - index1

        cursor.execute("""
            INSERT INTO upper_trendlines (ticker, date1, date2, slope, date_diff, index2)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker) DO UPDATE
            SET date1 = EXCLUDED.date1,
                date2 = EXCLUDED.date2,
                slope = EXCLUDED.slope,
                date_diff = EXCLUDED.date_diff,
                index2 = EXCLUDED.index2;
        """, (stock, date1, best_date2, largest_negative_slope, date_diff, index2))
        connection.commit()

        print(f"Updated upper_trendlines for {stock}: Date1: {date1}, Date2: {best_date2}, Slope: {largest_negative_slope}, Date_diff: {date_diff}, Index2: {index2}")
    else:
        print(f"No valid trendline found for {stock}.")

@timed()
def find_and_update_upper_trendline_historical(stock, last_date):
    """
    Find the highest price and validate the trendline for a given stock up to a specific date.
    Similar to find_and_update_upper_trendline but with a last_date parameter that ensures
    date2 cannot be higher than this date. Used for historical trendline simulation.
    Inserts the result into upper_trendlines_historical table.
    """

    # Convert last_date to datetime for comparison
    if isinstance(last_date, str):
        last_date = pd.to_datetime(last_date)

    # Fetch stock prices from the database up to last_date
    cursor.execute("""
        SELECT date, high
        FROM stock_prices
        WHERE ticker = %s AND date <= %s
        ORDER BY date;
    """, (stock, last_date))
    rows = cursor.fetchall()

    if not rows:
        print(f"No data found for {stock} up to {last_date}.")
        return

    # Convert the data into a DataFrame
    df = pd.DataFrame(rows, columns=['time', 'high'])
    df['time'] = pd.to_datetime(df['time'])
    df['high'] = df['high'].astype(float)

    # Extract unique trading dates and sort them
    trading_days = sorted(df['time'].unique())

    # Find the highest price and its date
    highest_row = df.loc[df['high'].idxmax()]
    date1 = highest_row['time']
    price1 = highest_row['high']

    # Initialize variables for the second point
    largest_negative_slope = float('-inf')
    best_date2 = None

    # Sort rows by 'high' in descending order for faster iteration
    # Only consider dates after date1 and up to last_date
    sorted_df = df[df['time'] > date1].sort_values(by='high', ascending=False)

    # Iterate through sorted rows
    for index, row in sorted_df.iterrows():
        date2 = row['time']
        price2 = row['high']

        # Check if the high price of date2 equals the high price of date1
        if price2 == price1:
            slope = 0
            index1 = trading_days.index(date1)
            index2 = trading_days.index(date2)
            date_diff = index2 - index1

            # Insert into upper_trendlines_historical table
            cursor.execute("""
                INSERT INTO upper_trendlines_historical (ticker, analysis_date, date1, date2, slope, date_diff, index2)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (stock, last_date, date1, date2, slope, date_diff, index2))
            connection.commit()

            print(f"Inserted historical upper trendline for {stock} (analysis_date: {last_date}): Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")
            return

        # Calculate the number of trading days between date1 and date2
        index1 = trading_days.index(date1)
        index2 = trading_days.index(date2)
        date_diff = index2 - index1
        if date_diff == 0:
            continue  # Avoid division by zero

        # Calculate the slope in log scale
        log_price1 = np.log(price1)
        log_price2 = np.log(price2)
        slope = (log_price2 - log_price1) / date_diff

        # If valid and the slope is the largest negative slope, update the best point
        if slope > largest_negative_slope:
            largest_negative_slope = slope
            best_date2 = date2

    largest_negative_slope = float(largest_negative_slope)

    # Insert the trendline data if a valid trendline is found
    if best_date2:
        index1 = trading_days.index(date1)
        index2 = trading_days.index(best_date2)
        date_diff = index2 - index1

        cursor.execute("""
            INSERT INTO upper_trendlines_historical (ticker, analysis_date, date1, date2, slope, date_diff, index2)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (stock, last_date, date1, best_date2, largest_negative_slope, date_diff, index2))
        connection.commit()

        print(f"Inserted historical upper trendline for {stock} (analysis_date: {last_date}): Date1: {date1}, Date2: {best_date2}, Slope: {largest_negative_slope}, Date_diff: {date_diff}, Index2: {index2}")
    else:
        print(f"No valid trendline found for {stock} up to {last_date}.")

@timed()
def check_and_update_upper_trendline(stock, updated_dates):
    # Fetch the last date where `update_trendline = True`

    for date in updated_dates:
        cursor.execute("""
            SELECT MAX(date)
            FROM upper_status
            WHERE ticker = %s AND update_trendline = TRUE AND date = %s;
        """, (stock, date))
        last_update_trendline_date = cursor.fetchone()[0]

        if not last_update_trendline_date:
            print(f"No update for upper trendline set to True for {stock}. No action needed.")
            continue

        # Fetch the current date2 from upper_trendlines
        cursor.execute("""
            SELECT date2
            FROM upper_trendlines
            WHERE ticker = %s;
        """, (stock,))
        result = cursor.fetchone()

        if not result:
            raise ValueError(f"No trendline data found for {stock} in upper_trendlines.")

        current_date2 = result[0]

        if last_update_trendline_date > current_date2:
            print(f"Triggering trendline update for {stock}.")
            find_and_update_upper_trendline(stock)

@timed()
def find_and_update_under_trendline(stock):
    """
    Find the highest price and validate the trendline for a given stock.
    Update the under_trendlines table with new trendline data, including date_diff and index2.
    If the ticker is not found, a new row is inserted into under_trendlines.
    """

    # Fetch stock prices from the database
    cursor.execute("""
        SELECT date, low
        FROM stock_prices
        WHERE ticker = %s
        ORDER BY date;
    """, (stock,))
    rows = cursor.fetchall()

    if not rows:
        print(f"No data found for {stock}.")
        return

    # Convert the data into a DataFrame
    df = pd.DataFrame(rows, columns=['time', 'low'])
    df['time'] = pd.to_datetime(df['time'])
    df['low'] = df['low'].astype(float)

    # Extract unique trading dates and sort them
    trading_days = sorted(df['time'].unique())

    # Find the highest price and its date
    highest_row = df.loc[df['low'].idxmin()]
    date1 = highest_row['time']
    price1 = highest_row['low']

    # Initialize variables for the second point
    lowest_positive_slope = float('+inf')
    best_date2 = None

    # Sort rows by 'high' in descending order for faster iteration
    sorted_df = df[df['time'] > date1].sort_values(by='low', ascending=False)

    # Iterate through sorted rows
    for index, row in sorted_df.iterrows():
        date2 = row['time']
        price2 = row['low']

        # Check if the high price of date2 equals the high price of date1
        if price2 == price1:
            slope = 0
            index1 = trading_days.index(date1)
            index2 = trading_days.index(date2)
            date_diff = index2 - index1

            # Try to update the under_trendlines table, if no rows found, insert new one
            cursor.execute("""
                        UPDATE under_trendlines
                        SET date1 = %s, date2 = %s, slope = %s, date_diff = %s, index2 = %s
                        WHERE ticker = %s;
                    """, (date1, date2, slope, date_diff, index2, stock))
            if cursor.rowcount == 0:  # If no rows were updated (ticker not found)
                cursor.execute("""
                    INSERT INTO under_trendlines (ticker, date1, date2, slope, date_diff, index2)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (stock, date1, date2, slope, date_diff, index2))
            connection.commit()

            print(
                f"Updated under_trendlines for {stock}: Date1: {date1}, Date2: {date2}, Slope: {slope},"
                f" Date_diff: {date_diff}, Index2: {index2}")
            return

        # Calculate the number of trading days between date1 and date2
        index1 = trading_days.index(date1)
        index2 = trading_days.index(date2)
        date_diff = index2 - index1
        if date_diff == 0:
            continue  # Avoid division by zero

        # Calculate the slope in log scale
        log_price1 = np.log(price1)
        log_price2 = np.log(price2)
        slope = (log_price2 - log_price1) / date_diff

        # If valid and the slope is the largest negative slope, update the best point
        if slope < lowest_positive_slope:
            lowest_positive_slope = slope
            best_date2 = date2

    lowest_positive_slope = float(lowest_positive_slope)

    # Update the under_trendlines table if a valid trendline is found
    if best_date2:
        index1 = trading_days.index(date1)
        index2 = trading_days.index(best_date2)
        date_diff = index2 - index1

        cursor.execute("""
            UPDATE under_trendlines
            SET date1 = %s, date2 = %s, slope = %s, date_diff = %s, index2 = %s
            WHERE ticker = %s;
        """, (date1, best_date2, lowest_positive_slope, date_diff, index2, stock))
        if cursor.rowcount == 0:  # If no rows were updated (ticker not found)
            cursor.execute("""
                INSERT INTO under_trendlines (ticker, date1, date2, slope, date_diff, index2)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (stock, date1, best_date2, lowest_positive_slope, date_diff, index2))
        connection.commit()

        print(f"Updated under_trendlines for {stock}: Date1: {date1}, Date2: {best_date2}, Slope: {lowest_positive_slope}, Date_diff: {date_diff}, Index2: {index2}")
    else:
        print(f"No valid trendline found for {stock}.")

@timed()
def check_and_update_under_trendline(stock, updated_dates):
    # Fetch the last date where `update_trendline = True`

    for date in updated_dates:
        cursor.execute("""
            SELECT MAX(date)
            FROM under_status
            WHERE ticker = %s AND update_trendline = TRUE AND date = %s;
        """, (stock, date))
        last_update_trendline_date = cursor.fetchone()[0]

        if not last_update_trendline_date:
            print(f"No update for under trendline set to True for {stock}. No action needed.")
            continue

        # Fetch the current date2 from upper_trendlines
        cursor.execute("""
            SELECT date2
            FROM under_trendlines
            WHERE ticker = %s;
        """, (stock,))
        result = cursor.fetchone()

        if not result:
            raise ValueError(f"No trendline data found for {stock} in under_trendlines.")

        current_date2 = result[0]

        if last_update_trendline_date > current_date2:
            print(f"Triggering trendline update for {stock}.")
            find_and_update_under_trendline(stock)

@timed()
def update_daily_move(ticker):
    try:
        query = """
        WITH price_data AS (
            SELECT
                ticker,
                date::date AS date,
                close,
                LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS yesterday_close
            FROM public.stock_prices
            WHERE ticker = %s
        )
        UPDATE public.stock_prices sp
        SET daily_move = ROUND(100 * (price_data.close - price_data.yesterday_close) / NULLIF(price_data.yesterday_close, 0), 2)
        FROM price_data
        WHERE sp.ticker = price_data.ticker
          AND sp.date::date = price_data.date
          AND price_data.yesterday_close IS NOT NULL
          AND price_data.yesterday_close != 0;
        """

        cursor.execute(query, (ticker,))
        connection.commit()
        print(f"✅ daily_move updated for {ticker}")

    except Exception as e:
        print(f"❌ Error for {ticker}: {e}")
        connection.rollback()  # VERY IMPORTANT

@timed()
def fetch_query(query, params=None):
    """Fetch query results from PostgreSQL."""
    with psycopg2.connect(**db_config) as conn:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(query, params if params else ())
            return cursor.fetchall()

@timed()
def update_upper_portfolio():
    upper_status_query = """
        SELECT date, ticker, breakthrough, update_trendline, trendline, duration_from_date2, distance, sequence
        FROM upper_status
        WHERE date = (SELECT MAX(date) FROM upper_status);
    """
    stock_prices_query = """
        SELECT date, ticker, close, low FROM stock_prices
        WHERE date = (SELECT MAX(date) FROM stock_prices);
    """

    res_ups = fetch_query(upper_status_query)
    if not res_ups:
        print("No data returned from upper_status.")
        return
    upper_status = pd.DataFrame(res_ups, columns=[
        "date", "ticker", "breakthrough", "update_trendline",
        "trendline", "duration_from_date2", "distance", "sequence"
    ])

    res_sp = fetch_query(stock_prices_query)
    if not res_sp:
        print("No data returned from stock_prices.")
        return
    stock_prices = pd.DataFrame(res_sp, columns=["date", "ticker", "close", "low"])

    open_positions = pd.read_csv("open_positions.csv") if os.path.exists("open_positions.csv") else pd.DataFrame(
        columns=["date", "action", "strategy", "ticker", "price", "Profit/Loss %", "SL", "TP"]
    )
    positions = pd.read_csv("positions.csv") if os.path.exists("positions.csv") else pd.DataFrame(
        columns=["date", "action", "strategy", "ticker", "price", "Profit/Loss %", "SL", "TP"]
    )

    merged_data = upper_status.merge(stock_prices, on=["date", "ticker"], how="inner")

    for _, row in merged_data.iterrows():
        ticker = row["ticker"]
        if (
            row["breakthrough"]
            and not row["update_trendline"]
            and row["close"] > row["trendline"]
            and row["duration_from_date2"] > 50
            and row["sequence"] == 1
            and ticker not in open_positions["ticker"].values
        ):
            sl = min(row["low"], row["trendline"])
            tp = round(float(row["close"]) * 1.1, 3)
            new_position = {
                "date": row["date"],
                "action": "buy",
                "strategy": "upper",
                "ticker": ticker,
                "price": row["close"],
                "Profit/Loss %": "0%",
                "SL": sl,
                "TP": tp
            }
            positions = pd.concat([positions, pd.DataFrame([new_position])], ignore_index=True)
            open_positions = pd.concat([open_positions, pd.DataFrame([new_position])], ignore_index=True)

    positions.to_csv("positions.csv", index=False)
    open_positions.to_csv("open_positions.csv", index=False)
    print("Upper Portfolio updated successfully.")

@timed()
def update_under_portfolio():
    under_status_query = """
        SELECT date, ticker, breakthrough, update_trendline, trendline, duration_from_date2, distance, sequence
        FROM under_status
        WHERE date = (SELECT MAX(date) FROM under_status);
    """
    stock_prices_query = """
        SELECT date, ticker, close, low FROM stock_prices
        WHERE date = (SELECT MAX(date) FROM stock_prices);
    """

    res_ups = fetch_query(under_status_query)
    if not res_ups:
        print("No data returned from under_status. Aborting update_portfolio.")
        return
    under_status = pd.DataFrame(res_ups, columns=[
        "date", "ticker", "breakthrough", "update_trendline",
        "trendline", "duration_from_date2", "distance", "sequence"
    ])

    res_sp = fetch_query(stock_prices_query)
    if not res_sp:
        print("No data returned from stock_prices. Aborting update_portfolio.")
        return
    stock_prices = pd.DataFrame(res_sp, columns=["date", "ticker", "close", "low"])

    open_positions = pd.read_csv("open_positions.csv") if os.path.exists("open_positions.csv") else pd.DataFrame(
        columns=["date", "action", "strategy", "ticker", "price", "Profit/Loss %", "SL", "TP"]
    )
    positions = pd.read_csv("positions.csv") if os.path.exists("positions.csv") else pd.DataFrame(
        columns=["date", "action", "strategy", "ticker", "price", "Profit/Loss %", "SL", "TP"]
    )

    merged_data = under_status.merge(stock_prices, on=["date", "ticker"], how="inner")

    for _, row in merged_data.iterrows():
        ticker = row["ticker"]
        if (
            row["distance"] < 0
            and row["distance"] > -5
            and row["low"] <= row["trendline"]
            and row["duration_from_date2"] > 50
            and ticker not in open_positions["ticker"].values
        ):
            new_position = {
                "date": row["date"],
                "action": "buy",
                "strategy": "under",
                "ticker": ticker,
                "price": row["close"],
                "Profit/Loss %": "0%",
                "SL": row["low"],
                "TP": round(float(row["close"]) * 1.1, 3)
            }
            positions = pd.concat([positions, pd.DataFrame([new_position])], ignore_index=True)
            open_positions = pd.concat([open_positions, pd.DataFrame([new_position])], ignore_index=True)

    positions.to_csv("positions.csv", index=False)
    open_positions.to_csv("open_positions.csv", index=False)
    print("Under Portfolio updated successfully.")

@timed()
def update_under_open_positions():
    stock_prices_query = """
        SELECT date, ticker, high, low, close FROM stock_prices
        WHERE date = (SELECT MAX(date) FROM stock_prices);
    """
    res_sp = fetch_query(stock_prices_query)
    if not res_sp:
        print("No stock price data returned.")
        return
    stock_prices = pd.DataFrame(res_sp, columns=["date", "ticker", "high", "low", "close"])

    under_status_query = """
        SELECT ticker, distance FROM under_status
        WHERE date = (SELECT MAX(date) FROM under_status);
    """
    res_ups = fetch_query(under_status_query)
    under_status = pd.DataFrame(res_ups, columns=["ticker", "distance"]) if res_ups else pd.DataFrame(columns=["ticker", "distance"])

    open_positions = pd.read_csv("open_positions.csv")
    positions = pd.read_csv("positions.csv")

    last_date = pd.to_datetime(stock_prices["date"].max()).date()
    closed_positions = []
    updated_open_positions = []

    for _, row in open_positions.iterrows():
        ticker = row["ticker"]
        entry_date = pd.to_datetime(row["date"]).date()
        entry_price = float(row["price"])
        sl = float(row["SL"])
        tp = float(row["TP"])

        stock_data = stock_prices[stock_prices["ticker"] == ticker]
        if stock_data.empty:
            continue

        current = stock_data.iloc[0]
        current_date = pd.to_datetime(current["date"]).date()
        close = float(current["close"])
        high = float(current["high"])
        low = float(current["low"])

        profit_loss = ((close - entry_price) / entry_price) * 100

        if current_date == entry_date:
            updated_open_positions.append({
                "date": entry_date,
                "action": row["action"],
                "strategy": row["strategy"],
                "ticker": ticker,
                "price": close,
                "Profit/Loss %": f"{round(profit_loss, 2)}%",
                "SL": sl,
                "TP": tp
            })
            continue

        if high >= tp or low <= sl:
            sell_price = tp if high >= tp else sl
            profit_loss = ((sell_price - entry_price) / entry_price) * 100
            closed_positions.append({
                "date": current_date,
                "action": "sell",
                "strategy": "under",
                "ticker": ticker,
                "price": sell_price,
                "Profit/Loss %": round(profit_loss, 2),
                "SL": sl,
                "TP": tp
            })
            open_positions = open_positions[open_positions["ticker"] != ticker]
        else:
            updated_open_positions.append({
                "date": entry_date,
                "action": row["action"],
                "strategy": row["strategy"],
                "ticker": ticker,
                "price": close,
                "Profit/Loss %": f"{round(profit_loss, 2)}%",
                "SL": sl,
                "TP": tp
            })

    if closed_positions:
        positions = pd.concat([positions, pd.DataFrame(closed_positions)], ignore_index=True)

    positions.to_csv("positions.csv", index=False)
    pd.DataFrame(updated_open_positions).to_csv("open_positions.csv", index=False)
    print("Under open positions updated successfully.")


@timed()
def update_upper_open_positions():
    import pandas as pd

    # Load open positions
    open_positions = pd.read_csv("open_positions.csv")
    if open_positions.empty:
        print("No open positions to update.")
        return

    tracked_tickers = open_positions["ticker"].tolist()
    tickers_str = ",".join(f"'{ticker}'" for ticker in tracked_tickers)

    # Query latest stock data for tracked tickers
    stock_prices_query = f"""
        SELECT date, ticker, high, low, close FROM stock_prices
        WHERE date = (SELECT MAX(date) FROM stock_prices)
        AND ticker IN ({tickers_str});
    """
    res_sp = fetch_query(stock_prices_query)
    if not res_sp:
        print("No stock price data returned. Aborting.")
        return
    stock_prices = pd.DataFrame(res_sp, columns=["date", "ticker", "high", "low", "close"])
    last_date = stock_prices["date"].max()

    # Optional: distance from upper_status for SL adjustments (if you want to use it)
    upper_status_query = f"""
        SELECT ticker, distance FROM upper_status
        WHERE date = (SELECT MAX(date) FROM upper_status)
        AND ticker IN ({tickers_str});
    """
    res_ups = fetch_query(upper_status_query)
    upper_status = pd.DataFrame(res_ups, columns=["ticker", "distance"]) if res_ups else pd.DataFrame(columns=["ticker", "distance"])

    positions = pd.read_csv("positions.csv")
    updated_open_positions = []
    closed_positions = []

    for _, row in open_positions.iterrows():
        ticker = row["ticker"]
        entry_date = pd.to_datetime(row["date"]).date()
        entry_price = float(row["price"])
        sl = float(row["SL"])
        tp = float(row["TP"])

        stock_data = stock_prices[stock_prices["ticker"] == ticker]
        if stock_data.empty:
            continue

        current = stock_data.iloc[0]
        current_date = pd.to_datetime(current["date"]).date()
        close = float(current["close"])
        high = float(current["high"])
        low = float(current["low"])

        # Always update profit/loss
        profit_loss = ((close - entry_price) / entry_price) * 100

        if current_date == entry_date:
            updated_open_positions.append({
                "date": entry_date,
                "action": row["action"],
                "strategy": row["strategy"],
                "ticker": ticker,
                "price": close,
                "Profit/Loss %": f"{round(profit_loss, 2)}%",
                "SL": sl,
                "TP": tp
            })
            continue  # skip SL/TP check on entry day

        # SL/TP check
        if high >= tp or low <= sl:
            sell_price = tp if high >= tp else sl
            profit_loss = ((sell_price - entry_price) / entry_price) * 100
            closed_positions.append({
                "date": current_date,
                "action": "sell",
                "strategy": row["strategy"],
                "ticker": ticker,
                "price": sell_price,
                "Profit/Loss %": round(profit_loss, 2),
                "SL": sl,
                "TP": tp
            })
            open_positions = open_positions[open_positions["ticker"] != ticker]
        else:
            updated_open_positions.append({
                "date": entry_date,
                "action": row["action"],
                "strategy": row["strategy"],
                "ticker": ticker,
                "price": close,
                "Profit/Loss %": f"{round(profit_loss, 2)}%",
                "SL": sl,
                "TP": tp
            })

    # Save updates
    if closed_positions:
        positions = pd.concat([positions, pd.DataFrame(closed_positions)], ignore_index=True)
        print(f"Closed {len(closed_positions)} position(s).")

    positions.to_csv("positions.csv", index=False)
    pd.DataFrame(updated_open_positions).to_csv("open_positions.csv", index=False)
    print("Open positions updated successfully.")

@timed()
def find_close_upper_trendline(stock, d):
    """
    Find the highest price and validate the trendline for a given stock.
    Update the stock_dates table with new trendlines data.
    """

    if not 1 <= d <= 9:
        raise ValueError("Invalid column index. Must be between 1 and 9.")

    # Build query with column name directly in the SQL string
    query = f"""
        SELECT sp.date, sp.high
        FROM stock_prices sp
        JOIN stock_dates sd ON sp.ticker = sd.ticker
        WHERE sp.ticker = %s AND sp.date >= sd.d{d}
        ORDER BY sp.date;
    """

    # Execute with parameter for stock only
    cursor.execute(query, (stock,))
    rows = cursor.fetchall()

    if not rows:
        print(f"No data found for {stock}.")
        return -1

    # Convert the data into a DataFrame
    df = pd.DataFrame(rows, columns=['time', 'high'])
    df['time'] = pd.to_datetime(df['time'])
    df['high'] = df['high'].astype(float)

    # Extract unique trading dates and sort them
    trading_days = sorted(df['time'].unique())

    # Find the highest price and its date
    highest_row = df.loc[df['high'].idxmax()]
    date1 = highest_row['time']
    price1 = highest_row['high']

    # Initialize variables for the second point
    largest_negative_slope = float('-inf')
    best_date2 = None

    # Sort rows by 'high' in descending order for faster iteration
    sorted_df = df[df['time'] > date1].sort_values(by='high', ascending=False)

    # Iterate through sorted rows
    for index, row in sorted_df.iterrows():
        date2 = row['time']
        price2 = row['high']

        # Check if the high price of date2 equals the high price of date1
        if price2 == price1:
            slope = 0
            index1 = trading_days.index(date1)
            index2 = trading_days.index(date2)
            date_diff = index2 - index1

            col1 = f'd{d}'
            col2 = f'd{d + 1}'

            # Construct the query safely
            query = f"""
                UPDATE stock_dates
                SET {col2} = %s
                WHERE ticker = %s;
            """

            # Execute with values
            cursor.execute(query, (date2, stock))
            connection.commit()

            # print(f"Updated stock_dates for {stock}: {col1} = {date1}, {col2} = {date2}")
            return

        # Calculate the number of trading days between date1 and date2
        index1 = trading_days.index(date1)
        index2 = trading_days.index(date2)
        date_diff = index2 - index1
        if date_diff == 0:
            continue  # Avoid division by zero

        # Calculate the slope in log scale
        log_price1 = np.log(price1)
        log_price2 = np.log(price2)
        slope = (log_price2 - log_price1) / date_diff

        # If valid and the slope is the largest negative slope, update the best point
        if slope > largest_negative_slope:
            largest_negative_slope = slope
            best_date2 = date2

    largest_negative_slope = float(largest_negative_slope)

    # Update the upper_trendlines table if a valid trendline is found
    if best_date2:
        index1 = trading_days.index(date1)
        index2 = trading_days.index(best_date2)
        date_diff = index2 - index1

        col1 = f'd{d}'
        col2 = f'd{d + 1}'

        # Construct the query safely
        query = f"""
            UPDATE stock_dates
            SET {col2} = %s
            WHERE ticker = %s;
        """

        # Execute with values
        cursor.execute(query, (best_date2, stock))
        connection.commit()

        # print(f"Updated stock_dates for {stock}: {col1} = {date1}, {col2} = {best_date2}")
    else:
        # print(f"No valid trendline found for {stock}.")
        return -1

@timed()
def update_all_upper_trendlines(stock):
    print(f'find_close_upper_trendline for {stock}')
    for i in range(1, 9):
        if find_close_upper_trendline(stock, i) == -1:
            break

@timed()
def find_closest_trendline(stock, target_date):
    # Fetch stock_dates for this ticker
    cursor.execute("""
        SELECT d1, d2, d3, d4, d5, d6, d7, d8, d9, d10
        FROM stock_dates
        WHERE ticker = %s;
    """, (stock,))
    row = cursor.fetchone()
    if not row:
        print(f"No stock_dates found for {stock}")
        return

    # Filter out NULLs and convert to datetime
    stock_dates = [pd.to_datetime(d) for d in row if d is not None]
    if len(stock_dates) < 2:
        print(f"Not enough valid dates for {stock}")
        return

    # Fetch stock price data
    cursor.execute("""
        SELECT date, high, close
        FROM stock_prices
        WHERE ticker = %s
        ORDER BY date;
    """, (stock,))
    rows = cursor.fetchall()
    if not rows:
        print(f"No stock_prices found for {stock}")
        return

    data = pd.DataFrame(rows, columns=['date', 'high', 'close'])
    data['date'] = pd.to_datetime(data['date'])
    data['high'] = data['high'].astype(float)
    data['close'] = data['close'].astype(float)

    trading_days = sorted(data['date'].unique())
    if target_date not in trading_days:
        print(f"{target_date} not found in trading_days")
        return

    close_price = float(data.loc[data['date'] == target_date, 'close'].values[0])
    trendline_pairs = [(stock_dates[i], stock_dates[i + 1]) for i in range(len(stock_dates) - 1)]

    # REVERSE loop over date pairs: (d4,d5), (d3,d4), ...
    for i in range(len(stock_dates) - 1, 0, -1):
        d1 = stock_dates[i - 1]
        d2 = stock_dates[i]

        if d1 not in trading_days or d2 not in trading_days:
            continue

        try:
            trendline = calculate_upper_trendline(data, d1, d2)
            idx = trading_days.index(target_date)
            trendline_price = trendline[idx]
        except Exception:
            continue

        if trendline_price > close_price:
            trendline_level = None
            try:
                trendline_level = trendline_pairs.index((d1, d2)) + 1
            except ValueError:
                pass
            # Found the first one above — this is the closest
            index1 = trading_days.index(d1)
            index2 = trading_days.index(d2)
            date_diff = index2 - index1
            if date_diff == 0:
                return

            price1 = float(data.loc[data['date'] == d1, 'high'].values[0])
            price2 = float(data.loc[data['date'] == d2, 'high'].values[0])
            slope = (np.log(price2) - np.log(price1)) / date_diff

            cursor.execute("""
                INSERT INTO closest_trendline (ticker, date1, date2, slope, date_diff, index2, trendline_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker)
                DO UPDATE SET
                    date1 = EXCLUDED.date1,
                    date2 = EXCLUDED.date2,
                    slope = EXCLUDED.slope,
                    date_diff = EXCLUDED.date_diff,
                    index2 = EXCLUDED.index2,
                    trendline_level = EXCLUDED.trendline_level;
            """, (
                stock, d1, d2, slope, date_diff, index2, trendline_level
            ))

            connection.commit()
            print(f"✅ Closest trendline for {stock} is ({d1} → {d2})")
            return  # Stop after first valid match

    print(f"⚠️ No trendline above close price for {stock} on {target_date}")

@timed()
def update_closest_status(stock):
    """
    Update the closest_status table for a given stock using trendline from closest_trendline.
    """
    # 1. Fetch trendline info from closest_trendline
    cursor.execute("""
        SELECT date1, date2, slope, trendline_level
        FROM closest_trendline
        WHERE ticker = %s;
    """, (stock,))
    trendline_data = cursor.fetchone()

    if not trendline_data:
        raise ValueError(f"No closest_trendline data found for {stock}")

    date1, date2, slope, trendline_level = trendline_data

    # 2. Fetch full stock_dates to get hierarchy
    cursor.execute("""
        SELECT d1, d2, d3, d4, d5, d6, d7, d8, d9, d10
        FROM stock_dates
        WHERE ticker = %s;
    """, (stock,))
    row = cursor.fetchone()
    valid_dates = [pd.to_datetime(d) for d in row if d is not None]
    trendline_pairs = [(valid_dates[i], valid_dates[i + 1]) for i in range(len(valid_dates) - 1)]

    # 3. Fetch stock prices
    cursor.execute("""
        SELECT date, high, close
        FROM stock_prices
        WHERE ticker = %s
        ORDER BY date;
    """, (stock,))
    rows = cursor.fetchall()

    data = pd.DataFrame(rows, columns=['date', 'high', 'close'])
    data['date'] = pd.to_datetime(data['date'])
    data['high'] = data['high'].astype(float)
    data['close'] = data['close'].astype(float)

    trading_days = sorted(data['date'].unique())
    trading_days_map = {day: idx for idx, day in enumerate(trading_days)}
    index1 = trading_days_map[pd.Timestamp(date1)]
    index2 = trading_days_map[pd.Timestamp(date2)]

    # 4. Calculate main trendline and metrics
    data['trendline'] = calculate_upper_trendline(data, date1, date2)
    data['distance'] = ((data['trendline'] - data['close']) / data['close']) * 100
    data['breakthrough'] = data['close'] > data['trendline']
    data['duration_from_date1'] = data['date'].apply(lambda x: trading_days_map[x] - index1)
    data['duration_from_date2'] = data['date'].apply(lambda x: trading_days_map[x] - index2)
    data['sequence'] = calculate_sequence(data['breakthrough'])

    data['previous_breakthrough'] = data['breakthrough'].shift(1, fill_value=False)
    data['update_trendline'] = (
        (data['sequence'] > 10) |
        ((data['distance'] > 0) & (data['previous_breakthrough'])) |
        (data['distance'] < -10)
    )
    data.drop(columns=['previous_breakthrough'], inplace=True)

    # 5. If a next trendline exists (previous in hierarchy), calculate its price per date
    if trendline_level and trendline_level > 1 and trendline_level - 2 < len(trendline_pairs):
        next_pair_index = trendline_level - 2
        try:
            next_d1, next_d2 = trendline_pairs[next_pair_index]
            next_trendline = calculate_upper_trendline(data, next_d1, next_d2)
            data['distance_to_next_trendline'] = ((next_trendline - data['trendline']) / data['trendline']) * 100
        except Exception as e:
            print(f"⚠️ Failed to calculate next trendline for {stock}: {e}")
            data['distance_to_next_trendline'] = None
    else:
        data['distance_to_next_trendline'] = None

    # 6. Insert only new rows
    for _, row in data.iterrows():
        cursor.execute("""
            INSERT INTO closest_status (
                ticker, date, breakthrough, duration_from_date1, duration_from_date2,
                sequence, update_trendline, trendline, distance,
                distance_to_next_trendline, trendline_level
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, date) DO UPDATE SET
                breakthrough = EXCLUDED.breakthrough,
                duration_from_date1 = EXCLUDED.duration_from_date1,
                duration_from_date2 = EXCLUDED.duration_from_date2,
                sequence = EXCLUDED.sequence,
                update_trendline = EXCLUDED.update_trendline,
                trendline = EXCLUDED.trendline,
                distance = EXCLUDED.distance,
                distance_to_next_trendline = EXCLUDED.distance_to_next_trendline,
                trendline_level = EXCLUDED.trendline_level;
        """, (
            stock, row['date'], row['breakthrough'], row['duration_from_date1'],
            row['duration_from_date2'], row['sequence'], row['update_trendline'],
            row['trendline'], row['distance'], row['distance_to_next_trendline'],
            trendline_level
        ))

    connection.commit()
    print(f"✅ Updated closest_status for {stock}")

@timed()
def check_and_update_closest_trendline(stock, updated_dates):
    # Fetch the last date where `update_trendline = True`

    for date in updated_dates:
        cursor.execute("""
            SELECT MAX(date)
            FROM closest_status
            WHERE ticker = %s AND update_trendline = TRUE AND date = %s;
        """, (stock, date))
        last_update_trendline_date = cursor.fetchone()[0]

        if not last_update_trendline_date:
            print(f"No update for closest trendline set to True for {stock}. No action needed.")
            continue

        # Fetch the current date2 from upper_trendlines
        cursor.execute("""
                SELECT date2
                FROM closest_trendline
                WHERE ticker = %s;
            """, (stock,))
        result = cursor.fetchone()

        if not result:
            raise ValueError(f"No trendline data found for {stock} in upper_trendlines.")

        current_date2 = result[0]

        if last_update_trendline_date > current_date2:
            print(f"Triggering closest trendline update for {stock}.")
            find_closest_trendline(stock, pd.Timestamp(date))

