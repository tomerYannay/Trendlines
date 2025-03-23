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


def fetchDailyJson(symbol, prem_key='8LLD101ZZ48BBVC8'):
    """
    Fetch daily stock data for the given symbol using Alpha Vantage API.
    """
    api_url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize=full&apikey={prem_key}'
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


def add_close_high_low_open(symbol, prem_key='8LLD101ZZ48BBVC8'):
    time_series = fetchDailyJson(symbol, prem_key=prem_key)
    filtered_time_series = {
        date: values
        for date, values in time_series.items()
    }
    new_data = []
    for date, values in reversed(list(filtered_time_series.items())):
            open_price = float(values["1. open"])
            high_price = float(values["2. high"])
            low_price = float(values["3. low"])
            close_price = float(values["4. close"])
            adjusted_close = float(values["5. adjusted close"])
            volume = int(values["6. volume"])

            # Calculate the normalization factor
            normalization_factor = adjusted_close / close_price if close_price != 0 else 1.0

            # Normalize the prices
            normalized_open = round(open_price * normalization_factor, 2)
            normalized_high = round(high_price * normalization_factor, 2)
            normalized_low = round(low_price * normalization_factor, 2)
            normalized_close = round(adjusted_close, 2)

            # Append the normalized data
            new_data.append((
                symbol, date, normalized_open, normalized_high, normalized_low,
                normalized_close, volume
            ))

    # Insert the new data into the database
    if new_data:
        execute_values(
            cursor,
            """
            INSERT INTO stock_prices (ticker, date, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (ticker, date) DO NOTHING;
            """,
            new_data
        )
        connection.commit()
        print(f"Inserted {len(new_data)} new records for {symbol}.")
    else:
        print(f"No new data to update for {symbol}.")


def updateDBWithAPI(symbol, prem_key='8LLD101ZZ48BBVC8'):
    """
    Update the `stock_prices` table with new trading data fetched from the API.
    Normalize open, high, and low prices using the adjusted close price.
    """

    # Fetch the latest date in the database for the stock
    cursor.execute("SELECT MAX(date) FROM stock_prices WHERE ticker = %s;", (symbol,))
    latest_date_in_db = cursor.fetchone()[0]

    # Fetch data from the API
    time_series = fetchDailyJson(symbol, prem_key=prem_key)

    # Filter only if latest_date_in_db is not None
    if latest_date_in_db is not None:
        filtered_time_series = {
            date: values
            for date, values in time_series.items()
            if date > latest_date_in_db.strftime('%Y-%m-%d')
        }
    else:
        # No data in DB for this ticker, keep all time_series data
        filtered_time_series = time_series

    ema20_prices = None
    ma50_prices = None
    ma100_prices = None
    ma200_prices = None
    rsi_prices = None

    ema20_url = f"https://www.alphavantage.co/query?function=EMA&symbol={symbol}&interval=daily&time_period=20&series_type=close&apikey={prem_key}"
    response = requests.get(ema20_url)
    if response.status_code == 200:
        data = response.json()
        if "Technical Analysis: EMA" in data:
            ema20_prices = data['Technical Analysis: EMA']
        else:
            ema20_prices = None

    ma50_url = f"https://www.alphavantage.co/query?function=SMA&symbol={symbol}&interval=daily&time_period=50&series_type=close&apikey={prem_key}"
    response = requests.get(ma50_url)
    if response.status_code == 200:
        data = response.json()
        if "Technical Analysis: SMA" in data:
            ma50_prices = data['Technical Analysis: SMA']
        else:
            ma50_prices = None

    ma100_url = f"https://www.alphavantage.co/query?function=SMA&symbol={symbol}&interval=daily&time_period=100&series_type=close&apikey={prem_key}"
    response = requests.get(ma100_url)
    if response.status_code == 200:
        data = response.json()
        if "Technical Analysis: SMA" in data:
            ma100_prices = data['Technical Analysis: SMA']
        else:
            ma100_prices = None

    ma200_url = f"https://www.alphavantage.co/query?function=SMA&symbol={symbol}&interval=daily&time_period=200&series_type=close&apikey={prem_key}"
    response = requests.get(ma200_url)
    if response.status_code == 200:
        data = response.json()
        if "Technical Analysis: SMA" in data:
            ma200_prices = data['Technical Analysis: SMA']
        else:
            ma200_prices = None

    rsi_url = f"https://www.alphavantage.co/query?function=RSI&symbol={symbol}&interval=daily&time_period=14&series_type=close&apikey={prem_key}"
    response = requests.get(rsi_url)
    if response.status_code == 200:
        data = response.json()
        if "Technical Analysis: RSI" in data:
            rsi_prices = data['Technical Analysis: RSI']
        else:
            rsi_prices = None

    new_data = []
    updated_dates = []

    for date, values in reversed(list(filtered_time_series.items())):
        if latest_date_in_db is None or date > latest_date_in_db.strftime('%Y-%m-%d'):
            # Extract the raw and adjusted values
            open_price = float(values["1. open"])
            high_price = float(values["2. high"])
            low_price = float(values["3. low"])
            close_price = float(values["4. close"])
            adjusted_close = float(values["5. adjusted close"])
            volume = int(values["6. volume"])

            # Calculate the normalization factor
            normalization_factor = adjusted_close / close_price if close_price != 0 else 1.0

            # Normalize the prices
            normalized_open = round(open_price * normalization_factor, 2)
            normalized_high = round(high_price * normalization_factor, 2)
            normalized_low = round(low_price * normalization_factor, 2)
            normalized_close = round(adjusted_close, 2)

            try:
                ema20 = float(ema20_prices[date]["EMA"])
            except Exception as e:
                ema20 = None
                print(f'Error uploading ema20 for {symbol}: {e}')
            try:
                ma50 = float(ma50_prices[date]["SMA"])
            except Exception as e:
                ma50 = None
                print(f'Error uploading ma50 for {symbol}: {e}')
            try:
                ma100 = float(ma100_prices[date]["SMA"])
            except Exception as e:
                ma100 = None
                print(f'Error uploading ma100 for {symbol}: {e}')
            try:
                ma200 = float(ma200_prices[date]["SMA"])
            except Exception as e:
                ma200 = None
                print(f'Error uploading ma200 for {symbol}: {e}')
            try:
                rsi = float(rsi_prices[date]["RSI"])
            except Exception as e:
                rsi = None
                print(f'Error uploading RSI for {symbol}: {e}')

            # Append the normalized data
            new_data.append((
                symbol, date, normalized_open, normalized_high, normalized_low,
                normalized_close, volume, ema20, ma50, ma100, ma200, rsi
            ))
            updated_dates.append(date)
        else:
            break

    # Insert the new data into the database
    if new_data:
        execute_values(
            cursor,
            """
            INSERT INTO stock_prices (ticker, date, open, high, low, close, volume, ema20, ma50, ma100, ma200, rsi)
            VALUES %s
            ON CONFLICT (ticker, date) DO NOTHING;
            """,
            new_data
        )
        connection.commit()
        print(f"Inserted {len(new_data)} new records for {symbol}.")
    else:
        print(f"No new data to update for {symbol}.")

    return updated_dates


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

    # Check if breakthrough condition is met
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

    called_update_all = False
    # Insert rows for missing dates
    for _, row in data.iterrows():
        if row['date'] not in existing_dates:
            should_update = False

            if row['distance'] > 30:
                if last_update_date is None or (row['date'] - last_update_date).days >= 30:
                    should_update = True
                    last_update_date = row['date']  # Update reference for future rows
                    update_all_upper_trendlines(stock)

                    # Call update_all_upper_trendlines once
                    if not called_update_all:
                        update_all_upper_trendlines(stock)
                        called_update_all = True

            update_all_lines_date = row['date'] if should_update else None

            cursor.execute("""
                INSERT INTO upper_status (ticker, date, trendline, distance, breakthrough, duration_from_date1, duration_from_date2, sequence, update_trendline)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                stock, row['date'], row['trendline'], row['distance'], row['breakthrough'],
                row['duration_from_date1'], row['duration_from_date2'], row['sequence'], row['update_trendline']
            ))

    connection.commit()
    print(f"Updated upper_status for {stock}")


def calculate_upper_trendline(data, date1, date2):
    """
    Calculate trendline prices using logarithmic scale.
    This method follows the same logic as your earlier implementation but is made reusable.
    """
    # Locate indices for date1 and date2
    trading_days = sorted(data['date'].unique())
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

            # Update the upper_trendlines table immediately
            cursor.execute("""
                        UPDATE upper_trendlines
                        SET date1 = %s, date2 = %s, slope = %s, date_diff = %s, index2 = %s
                        WHERE ticker = %s;
                    """, (date1, date2, slope, date_diff, index2, stock))
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
            UPDATE upper_trendlines
            SET date1 = %s, date2 = %s, slope = %s, date_diff = %s, index2 = %s
            WHERE ticker = %s;
        """, (date1, best_date2, largest_negative_slope, date_diff, index2, stock))
        connection.commit()

        print(f"Updated upper_trendlines for {stock}: Date1: {date1}, Date2: {best_date2}, Slope: {largest_negative_slope}, Date_diff: {date_diff}, Index2: {index2}")
    else:
        print(f"No valid trendline found for {stock}.")


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
            find_and_update_upper_trendline(stock)


def update_daily_move(ticker):
    try:
        # Define the query with the provided ticker
        query = """
        WITH price_data AS (
            SELECT
                ticker,
                date,
                close,
                LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS yesterday_close
            FROM public.stock_prices
            WHERE ticker = %s
        )
        UPDATE public.stock_prices sp
        SET daily_move = ROUND(100 * (pd.close - pd.yesterday_close) / pd.yesterday_close, 2)
        FROM price_data pd
        WHERE sp.ticker = pd.ticker
          AND sp.date = pd.date
          AND pd.yesterday_close IS NOT NULL;
        """

        # Execute the query with the ticker parameter
        cursor.execute(query, (ticker,))

        # Commit the transaction
        connection.commit()
        print(f"Daily move updated successfully for ticker {ticker}.")

    except Exception as e:
        print(f"An error occurred: {e}")


def fetch_query(query, params=None):
    """Fetch query results from PostgreSQL."""
    with psycopg2.connect(**db_config) as conn:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(query, params if params else ())
            return cursor.fetchall()


def update_upper_portfolio():

    # Load data from database
    upper_status_query = """
        SELECT date, ticker, breakthrough, update_trendline, trendline, duration_from_date2, distance, sequence
        FROM upper_status
        WHERE date = (SELECT MAX(date) FROM upper_status);
    """
    upper_status = pd.DataFrame(fetch_query(upper_status_query))

    stock_prices_query = """
        SELECT date, ticker, close, low FROM stock_prices
        WHERE date = (SELECT MAX(date) FROM stock_prices);
    """
    stock_prices = pd.DataFrame(fetch_query(stock_prices_query))

    res_ups = fetch_query(upper_status_query)
    if not res_ups:
        print("No data returned from upper_status. Aborting update_portfolio.")
        return
    upper_status = pd.DataFrame(res_ups)

    res_sp = fetch_query(stock_prices_query)
    if not res_sp:
        print("No data returned from stock_prices. Aborting update_portfolio.")
        return
    stock_prices = pd.DataFrame(res_sp)

    upper_status.columns = [
        "date", "ticker", "breakthrough",
        "update_trendline", "trendline",
        "duration_from_date2", "distance", "sequence"
    ]
    stock_prices.columns = [
        "date", "ticker", "close", "low"
    ]

    if not os.path.exists("open_positions.csv"):
        open_positions = pd.DataFrame(columns=["ticker"])
    else:
        open_positions = pd.read_csv("open_positions.csv")

    positions = pd.read_csv("positions.csv") if os.path.exists("positions.csv") else pd.DataFrame(
        columns=["date", "action", "strategy", "ticker", "price", "Profit/Loss %", "SL", "TP"])

    merged_data = upper_status.merge(stock_prices, on=["date", "ticker"], how="inner")

    for _, row in merged_data.iterrows():
        ticker = row["ticker"]
        if row["breakthrough"] and not row["update_trendline"] and row["close"] > row["trendline"] and row[
            "duration_from_date2"] > 50 and row["sequence"] == 1:
            if ticker not in open_positions["ticker"].values:
                new_position = {
                    "date": row["date"],
                    "action": "buy",
                    "strategy": "upper",
                    "ticker": ticker,
                    "price": row["close"],
                    "Profit/Loss %": 0,
                    "SL": row["low"],
                    "TP": float(row["close"]) * 1.1
                }
                positions = pd.concat([positions, pd.DataFrame([new_position])], ignore_index=True)
                open_positions = pd.concat([open_positions, pd.DataFrame([{"ticker": ticker}])], ignore_index=True)

    positions.to_csv("positions.csv", index=False)
    open_positions.to_csv("open_positions.csv", index=False)
    print("Upper Portfolio updated successfully.")


def update_under_portfolio():
    # Load data from database
    under_status_query = """
        SELECT date, ticker, breakthrough, update_trendline, trendline, duration_from_date2, distance, sequence
        FROM under_status
        WHERE date = (SELECT MAX(date) FROM under_status);
    """
    under_status = pd.DataFrame(fetch_query(under_status_query))

    stock_prices_query = """
        SELECT date, ticker, close, low FROM stock_prices
        WHERE date = (SELECT MAX(date) FROM stock_prices);
    """
    stock_prices = pd.DataFrame(fetch_query(stock_prices_query))

    res_ups = fetch_query(under_status_query)
    if not res_ups:
        print("No data returned from under_status. Aborting update_portfolio.")
        return
    under_status = pd.DataFrame(res_ups)

    res_sp = fetch_query(stock_prices_query)
    if not res_sp:
        print("No data returned from stock_prices. Aborting update_portfolio.")
        return
    stock_prices = pd.DataFrame(res_sp)

    under_status.columns = [
        "date", "ticker", "breakthrough",
        "update_trendline", "trendline",
        "duration_from_date2", "distance", "sequence"
    ]
    stock_prices.columns = [
        "date", "ticker", "close", "low"
    ]

    if not os.path.exists("open_positions.csv"):
        open_positions = pd.DataFrame(columns=["ticker"])
    else:
        open_positions = pd.read_csv("open_positions.csv")

    positions = pd.read_csv("positions.csv") if os.path.exists("positions.csv") else pd.DataFrame(
        columns=["date", "action", "strategy", "ticker", "price", "Profit/Loss %", "SL", "TP"])

    merged_data = under_status.merge(stock_prices, on=["date", "ticker"], how="inner")

    for _, row in merged_data.iterrows():
        ticker = row["ticker"]
        if row["distance"] < 0 and row["distance"] > -5 and row["low"] <= row["trendline"] and row["duration_from_date2"] > 50:
            if ticker not in open_positions["ticker"].values:
                new_position = {
                    "date": row["date"],
                    "action": "buy",
                    "strategy": "under",
                    "ticker": ticker,
                    "price": row["close"],
                    "Profit/Loss %": 0,
                    "SL": row["low"],
                    "TP": float(row["close"]) * 1.1
                }
                positions = pd.concat([positions, pd.DataFrame([new_position])], ignore_index=True)
                open_positions = pd.concat([open_positions, pd.DataFrame([{"ticker": ticker}])], ignore_index=True)

    positions.to_csv("positions.csv", index=False)
    open_positions.to_csv("open_positions.csv", index=False)
    print("Under Portfolio updated successfully.")


def update_under_open_positions():
    # Load stock price data from database
    stock_prices_query = """
        SELECT date, ticker, high, low, close FROM stock_prices
        WHERE date = (SELECT MAX(date) FROM stock_prices);
    """
    stock_prices = pd.DataFrame(fetch_query(stock_prices_query))

    under_status_query = """
        SELECT ticker, distance FROM under_status
        WHERE date = (SELECT MAX(date) FROM under_status);
    """
    under_status = pd.DataFrame(fetch_query(under_status_query))

    open_positions = pd.read_csv("open_positions.csv")
    positions = pd.read_csv("positions.csv")

    last_date = stock_prices["date"].max()
    closed_positions = []

    for _, row in open_positions.iterrows():
        ticker = row["ticker"]
        stock_data = stock_prices[stock_prices["ticker"] == ticker]
        distance_data = under_status[under_status["ticker"] == ticker]

        if not stock_data.empty:
            high, low, close = stock_data.iloc[0][["high", "low", "close"]]
            distance = distance_data.iloc[0]["distance"] if not distance_data.empty else 0
            position = positions[positions["ticker"] == ticker].iloc[-1]
            sl, tp, buy_price = min(low, distance) if distance > 0 else low, position["TP"], position["price"]

            if high > tp or low < sl:
                sell_price = tp if high > tp else sl
                profit_loss = ((sell_price - buy_price) / buy_price) * 100
                closed_positions.append({
                    "date": last_date,
                    "strategy": "under",
                    "ticker": ticker,
                    "price": sell_price,
                    "Profit/Loss %": round(profit_loss, 2)
                })
                open_positions = open_positions[open_positions["ticker"] != ticker]  # Remove closed position

    if closed_positions:
        positions = pd.concat([positions, pd.DataFrame(closed_positions)], ignore_index=True)

    positions.to_csv("positions.csv", index=False)
    open_positions.to_csv("open_positions.csv", index=False)
    print("Open positions updated successfully.")


def update_upper_open_positions():
    # Load stock price data from database
    stock_prices_query = """
        SELECT date, ticker, high, low, close FROM stock_prices
        WHERE date = (SELECT MAX(date) FROM stock_prices);
    """
    stock_prices = pd.DataFrame(fetch_query(stock_prices_query))

    upper_status_query = """
        SELECT ticker, distance FROM upper_status
        WHERE date = (SELECT MAX(date) FROM upper_status);
    """
    upper_status = pd.DataFrame(fetch_query(upper_status_query))

    open_positions = pd.read_csv("open_positions.csv")
    positions = pd.read_csv("positions.csv")

    last_date = stock_prices["date"].max()
    closed_positions = []

    for _, row in open_positions.iterrows():
        ticker = row["ticker"]
        stock_data = stock_prices[stock_prices["ticker"] == ticker]
        distance_data = upper_status[upper_status["ticker"] == ticker]

        if not stock_data.empty:
            high, low, close = stock_data.iloc[0][["high", "low", "close"]]
            distance = distance_data.iloc[0]["distance"] if not distance_data.empty else 0
            position = positions[positions["ticker"] == ticker].iloc[-1]
            sl, tp, buy_price = min(low, distance) if distance > 0 else low, position["TP"], position["price"]

            if high > tp or low < sl:
                sell_price = tp if high > tp else sl
                profit_loss = ((sell_price - buy_price) / buy_price) * 100
                closed_positions.append({
                    "date": last_date,
                    "strategy": "upper",
                    "ticker": ticker,
                    "price": sell_price,
                    "Profit/Loss %": round(profit_loss, 2)
                })
                open_positions = open_positions[open_positions["ticker"] != ticker]  # Remove closed position

    if closed_positions:
        positions = pd.concat([positions, pd.DataFrame(closed_positions)], ignore_index=True)

    positions.to_csv("positions.csv", index=False)
    open_positions.to_csv("open_positions.csv", index=False)
    print("Open positions updated successfully.")


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

            print(f"Updated stock_dates for {stock}: {col1} = {date1}, {col2} = {date2}")
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

        print(f"Updated stock_dates for {stock}: {col1} = {date1}, {col2} = {best_date2}")
    else:
        print(f"No valid trendline found for {stock}.")
        return -1


def update_all_upper_trendlines(stock):
    for i in range(1, 9):
        print(i)
        if find_close_upper_trendline(stock, i) == -1:
            break
