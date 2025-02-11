import numpy as np
import pandas as pd
import psycopg2

db_config = {
    'dbname': 'stock_data',      # Name of your database
    'user': 'shimonyannay',          # Your PostgreSQL username
    'password': 'Apple2020', # Your PostgreSQL password
    'host': 'localhost',         # Hostname (localhost for local)
    'port': 5432                 # Default PostgreSQL port
}

# Connect to the database
connection = psycopg2.connect(**db_config)
cursor = connection.cursor()


def find_and_update_upper_trendline(stock):
    """
    Find the highest price and validate the trendline for a given stock.
    Update the stock_trendlines table with new trendline data, including date_diff and index2.
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

            # Update the stock_trendlines table immediately
            cursor.execute("""
                        UPDATE stock_trendlines
                        SET date1 = %s, date2 = %s, slope = %s, date_diff = %s, index2 = %s
                        WHERE ticker = %s;
                    """, (date1, date2, slope, date_diff, index2, stock))
            connection.commit()
            print(
                f"Updated stock_trendlines for {stock}: Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")
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

    # Update the stock_trendlines table if a valid trendline is found
    if best_date2:
        index1 = trading_days.index(date1)
        index2 = trading_days.index(best_date2)
        date_diff = index2 - index1

        cursor.execute("""
            UPDATE stock_trendlines
            SET date1 = %s, date2 = %s, slope = %s, date_diff = %s, index2 = %s
            WHERE ticker = %s;
        """, (date1, best_date2, largest_negative_slope, date_diff, index2, stock))
        connection.commit()

        print(f"Updated stock_trendlines for {stock}: Date1: {date1}, Date2: {best_date2}, Slope: {largest_negative_slope}, Date_diff: {date_diff}, Index2: {index2}")
    else:
        print(f"No valid trendline found for {stock}.")


def check_and_update_trendline(stock):
    # Fetch the last date where `update_trendline = True`
    cursor.execute("""
        SELECT MAX(date)
        FROM stock_prices
        WHERE ticker = %s AND update_trendline = TRUE;
    """, (stock,))
    last_update_trendline_date = cursor.fetchone()[0]

    if not last_update_trendline_date:
        print(f"No update_trendline set to True for {stock}. No action needed.")
        return

    # Fetch the current date2 from stock_trendlines
    cursor.execute("""
        SELECT date2
        FROM stock_trendlines
        WHERE ticker = %s;
    """, (stock,))
    result = cursor.fetchone()

    if not result:
        raise ValueError(f"No trendline data found for {stock} in stock_trendlines.")

    current_date2 = result[0]

    if last_update_trendline_date > current_date2:
        print(f"Triggering trendline update for {stock}.")
        find_and_update_upper_trendline(stock)


def find_and_update_trendline(stock):
    """
    Find the highest price and validate the trendline for a given stock.
    Update the stock_trendlines table with new trendline data, including date_diff and index2.
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

    # Fetch current trendline data from the stock_trendlines table
    cursor.execute("""
        SELECT date1, date2
        FROM stock_trendlines
        WHERE ticker = %s;
    """, (stock,))
    trendline_data = cursor.fetchone()

    if trendline_data:
        current_date1, current_date2 = map(pd.to_datetime, trendline_data)
    else:
        current_date1, current_date2 = None, None

    # Find the highest price and its date
    highest_row = df.loc[df['high'].idxmax()]
    date1 = highest_row['time']
    price1 = highest_row['high']

    # Initialize variables for the second point
    largest_negative_slope = float('-inf')
    best_date2 = None
    best_price2 = None
    min_slope = -100

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

            # Update the stock_trendlines table immediately
            cursor.execute("""
                        UPDATE stock_trendlines
                        SET date1 = %s, date2 = %s, slope = %s, date_diff = %s, index2 = %s
                        WHERE ticker = %s;
                    """, (date1, date2, slope, date_diff, index2, stock))
            connection.commit()
            print(
                f"Updated stock_trendlines for {stock}: Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")
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

        # Only consider negative slopes
        if slope >= 0 or round(slope, 7) < round(min_slope, 7):
            continue

        # Validate trendline by checking intermediate rows
        is_valid = True
        intermediate_rows = df[(df['time'] > date1) & (df['time'] < date2)]
        for _, mid_row in intermediate_rows.iterrows():
            # Calculate the trendline price at mid_row
            mid_index = trading_days.index(mid_row['time'])
            trading_days_to_mid_row = mid_index - index1
            log_trend_price = log_price1 + slope * trading_days_to_mid_row
            trend_price = np.exp(log_trend_price)

            # Check if the high price exceeds the trendline
            if mid_row['high'] > trend_price:
                is_valid = False
                min_slope = slope
                break

        # If valid and the slope is the largest negative slope, update the best point
        if is_valid and slope > largest_negative_slope:
            largest_negative_slope = slope
            best_date2 = date2
            best_price2 = price2

    largest_negative_slope = float(largest_negative_slope)

    # Update the stock_trendlines table if a valid trendline is found
    if best_date2:
        index1 = trading_days.index(date1)
        index2 = trading_days.index(best_date2)
        date_diff = index2 - index1

        cursor.execute("""
            UPDATE stock_trendlines
            SET date1 = %s, date2 = %s, slope = %s, date_diff = %s, index2 = %s
            WHERE ticker = %s;
        """, (date1, best_date2, largest_negative_slope, date_diff, index2, stock))
        connection.commit()

        print(f"Updated stock_trendlines for {stock}: Date1: {date1}, Date2: {best_date2}, Slope: {largest_negative_slope}, Date_diff: {date_diff}, Index2: {index2}")
    else:
        print(f"No valid trendline found for {stock}.")


def check_and_update_trendline1(stock):
    # Fetch the last date where `update_trendline = True`
    cursor.execute("""
        SELECT MAX(date)
        FROM stock_prices
        WHERE ticker = %s AND update_trendline = TRUE;
    """, (stock,))
    last_update_trendline_date = cursor.fetchone()[0]

    if not last_update_trendline_date:
        print(f"No update_trendline set to True for {stock}. No action needed.")
        return

    # Fetch the current date2 from stock_trendlines
    cursor.execute("""
        SELECT date2
        FROM stock_trendlines
        WHERE ticker = %s;
    """, (stock,))
    result = cursor.fetchone()

    if not result:
        raise ValueError(f"No trendline data found for {stock} in stock_trendlines.")

    current_date2 = result[0]

    if last_update_trendline_date > current_date2:
        print(f"Triggering trendline update for {stock}.")
        find_and_update_trendline(stock)


def update_status(stock):
    """
    Update the new columns in the stock_prices table for a given stock
    """

    # Fetch trendline data from stock_trendlines
    cursor.execute("""
        SELECT date1, date2, slope
        FROM stock_trendlines
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
    data['trendline'] = calculate_trendline(data, date1, date2)
    data['distance'] = ((data['trendline'].astype(float) - data['close']) / data['close']) * 100
    data['breakthrough'] = data['high'] > data['trendline']
    # Calculate durations in trading days
    data['duration_from_date1'] = data['date'].apply(lambda x: trading_days_map[x] - index1)
    data['duration_from_date2'] = data['date'].apply(lambda x: trading_days_map[x] - index2)
    data['sequence'] = calculate_sequence(data['breakthrough'])

    # Add a column for `update_trendline` based on the conditions
    data['previous_breakthrough'] = data['breakthrough'].shift(1, fill_value=False)
    data['update_trendline'] = (
            (data['sequence'] > 50) |
            ((~data['breakthrough']) & (data['previous_breakthrough'])) |
            (data['distance'] < -20)
    )

    # Drop temporary column
    data.drop(columns=['previous_breakthrough'], inplace=True)

    # Update the table
    for _, row in data.iterrows():
        cursor.execute("""
            UPDATE stock_prices
            SET trendline = %s,
                distance = %s,
                breakthrough = %s,
                duration_from_date1 = %s,
                duration_from_date2 = %s,
                sequence = %s,
                update_trendline = %s
            WHERE ticker = %s AND date = %s;
        """, (
            row['trendline'], row['distance'], row['breakthrough'],
            row['duration_from_date1'], row['duration_from_date2'],
            row['sequence'], row['update_trendline'], stock, row['date']
        ))

    connection.commit()
    print(f"Updated stock_prices for {stock}")