import os
import time
import pandas as pd
import requests
import numpy as np
from collections import Counter
import matplotlib.dates as mdates
from matplotlib import pyplot as plt
from scipy.signal import find_peaks
from datetime import datetime, timedelta
import psycopg2


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


def updateCSVWithAPI(symbol, existing_csv_path, prem_key='8LLD101ZZ48BBVC8'):
    """
    Update an existing CSV file with new trading data fetched from the API.
    Normalize open, high, and low prices using the adjusted close price.
    """
    if os.path.exists(existing_csv_path):
        existing_df = pd.read_csv(existing_csv_path)
        if not existing_df.empty:
            latest_date_in_csv = existing_df['time'].max()
        else:
            latest_date_in_csv = None
    else:
        existing_df = pd.DataFrame(columns=["time", "open", "high", "low", "close", "Volume"])
        latest_date_in_csv = None

    # Fetch data from the API
    time_series = fetchDailyJson(symbol, prem_key=prem_key)

    new_data = []
    for date, values in time_series.items():
        if latest_date_in_csv is None or date > latest_date_in_csv:
            # Extract the raw and adjusted values
            open_price = float(values["1. open"])
            high_price = float(values["2. high"])
            low_price = float(values["3. low"])
            close_price = float(values["4. close"])
            adjusted_close = float(values["5. adjusted close"])
            volume = int(values["6. volume"])

            # Calculate the normalization factor
            if close_price != 0:  # Avoid division by zero
                normalization_factor = adjusted_close / close_price
            else:
                normalization_factor = 1.0  # Default to no adjustment

            # Normalize the prices
            normalized_open = round(open_price * normalization_factor, 2)
            normalized_high = round(high_price * normalization_factor, 2)
            normalized_low = round(low_price * normalization_factor, 2)
            normalized_close = round(adjusted_close, 2)  # Use the adjusted close directly

            # Append the normalized data
            new_data.append({
                "time": date,
                "open": normalized_open,
                "high": normalized_high,
                "low": normalized_low,
                "close": normalized_close,
                "volume": volume
            })

    # Convert the new data to a DataFrame
    if new_data:
        new_df = pd.DataFrame(new_data)
        updated_df = pd.concat([existing_df, new_df], ignore_index=True)
        updated_df = updated_df.sort_values(by="time").reset_index(drop=True)
        updated_df.to_csv(existing_csv_path, index=False)
        print(f"Updated {existing_csv_path} with {len(new_data)} new records.")
    else:
        print(f"No new data to update for {symbol}.")


def get_valid_negative_slope_trend_lines(stock, dist):
    # Load data
    data = pd.read_csv(f'alpha/{stock}.csv')
    data['Date'] = pd.to_datetime(data['time'])
    data.set_index('Date', inplace=True)
    # Use 'high' and 'close' columns for prices
    prices_high = data['high']
    prices_close = data['close']
    prices_open = data['open']

    # Find peaks (local maxima)
    peaks, _ = find_peaks(prices_high, distance=dist)

    # Store valid trend lines
    valid_trend_lines = []

    # Iterate over pairs of consecutive peaks
    for i in range(len(peaks) - 1):
        start_idx = peaks[i]
        end_idx = peaks[i + 1]

        # Coordinates of the start and end peaks
        x_start = prices_high.index[start_idx]
        x_end = prices_high.index[end_idx]
        y_start = prices_high.iloc[start_idx]
        y_end = prices_high.iloc[end_idx]

        # Convert prices to logarithmic scale
        log_y_start = np.log(y_start)
        log_y_end = np.log(y_end)

        # Calculate the slope and intercept of the trend line in log scale
        slope = (log_y_end - log_y_start) / (x_end - x_start).days
        intercept = log_y_start - slope * x_start.to_pydatetime().toordinal()

        # Only consider negative slopes
        if slope >= 0:
            continue

        # Verify no intermediate highs exceed the trend line (with tolerance)
        is_valid = True
        for date in prices_high.index[start_idx + 1:end_idx]:
            x = date.to_pydatetime().toordinal()
            high_price = prices_high.loc[date]
            close_price = prices_close.loc[date]
            open_price = prices_open.loc[date]

            # Trend line value in log scale
            log_trend_value = slope * x + intercept

            # Convert back to original scale
            trend_value = np.exp(log_trend_value)

            # Check if high price exceeds trend line by more than 2%
            if high_price > trend_value:
                is_valid = False
                break

            # Check if close price is outside the trend line
            if close_price > trend_value:
                is_valid = False
                break

            if open_price > trend_value:
                is_valid = False
                break

        # Store the trend line if valid
        if is_valid:
            valid_trend_lines.append({
                "Start Date": x_start,
                "End Date": x_end,
                "Start Price": y_start,
                "End Price": y_end,
                "Slope": slope
            })
    return valid_trend_lines


def loop_trend_lines_with_frequency(stock, start_dist=50, end_dist=1500, step=10):
    # Initialize a list to collect all trend lines
    all_trend_lines = []

    # Loop through the distance range
    for dist in range(start_dist, end_dist + 1, step):
        print(f"Processing distance: {dist}")
        trend_lines = get_valid_negative_slope_trend_lines(stock, dist)

        # If no trend lines found, break the loop
        if not trend_lines:
            print(f"No trend lines found for distance {dist}. Stopping.")

        # Convert trend lines to a hashable format (tuple) for counting
        for line in trend_lines:
            line_tuple = (
                line["Start Date"],
                line["End Date"],
                line["Start Price"],
                line["End Price"],
                line["Slope"]
            )
            all_trend_lines.append(line_tuple)

    # Count frequency of trend lines
    trend_line_counts = Counter(all_trend_lines)

    # Sort trend lines by frequency (most frequent first)
    sorted_trend_lines = trend_line_counts.most_common()

    # Convert back to a list of dictionaries for easier readability
    most_frequent_lines = [
        {
            "Start Date": line[0][0],
            "End Date": line[0][1],
            "Start Price": line[0][2],
            "End Price": line[0][3],
            "Slope": line[0][4],
            "Frequency": line[1]
        }
        for line in sorted_trend_lines
    ]

    return most_frequent_lines


def create_trend_lines(stock):
    try:
        most_frequent_trend_lines = loop_trend_lines_with_frequency(stock)
        most_frequent_df = pd.DataFrame(most_frequent_trend_lines)
        output_file = f"alpha/trend_lines/{stock}.csv"
        most_frequent_df.to_csv(output_file, index=False)
        print(f"Most frequent validated trend lines saved to {output_file}")

    except Exception as e:
        print(f'Error: {e}')
        return 0


def get_trend_line_price(trend_lines, target_date):
    trend_prices = []

    for line in trend_lines:
        # Extract data for the trend line
        start_date = pd.Timestamp(line["Start Date"])
        end_date = pd.Timestamp(line["End Date"])
        start_price = np.float64(line["Start Price"])
        end_price = np.float64(line["End Price"])

        # Convert dates to timestamps
        date1_num = start_date.timestamp()
        date2_num = end_date.timestamp()

        # Calculate log prices and slope in logarithmic scale
        log_price1 = np.log(start_price)
        log_price2 = np.log(end_price)
        log_slope = (log_price2 - log_price1) / (date2_num - date1_num)

        # Calculate the trend line price for the target date
        target_date_num = target_date.timestamp()
        log_trend_price = log_price1 + log_slope * (target_date_num - date1_num)

        # Convert back to the original scale
        trend_price = np.exp(log_trend_price)

        # Append the price and line details
        trend_prices.append((trend_price, line))

    return trend_prices


def analyze_price_breakthrough(data, yesterday_price, today_price, volume, today_date, trend_lines, historical_close_prices):
    today_date = pd.Timestamp(today_date)

    # Get all trend line prices for the target date
    trend_prices = get_trend_line_price(trend_lines, today_date)

    # Initialize variables to track the closest trend lines
    previous_trend_line = None
    next_trend_line = None
    next_trend_id = None
    previous_trend_id = None
    previous_trend_price = None
    next_trend_price = None
    min_prev_diff = float("inf")
    min_next_diff = float("inf")

    # Count the number of trend lines above the current close price
    trend_lines_above = -1

    # Load trading days (you can pass it as a parameter instead)
    trading_days = pd.date_range(start="2000-01-01", end="2025-12-31", freq="B")  # Business days
    trading_days = set(trading_days)

    # Iterate over trend prices to classify them
    for trend_price, line in trend_prices:
        if trend_price > today_price:
            # Increment the count of trend lines above
            trend_lines_above += 1

            # Closest above
            diff = trend_price - today_price
            if diff < min_next_diff:
                min_next_diff = diff
                next_trend_line = line
                next_trend_price = trend_price
                next_trend_id = line.get("ID", None)
        elif trend_price < today_price:
            # Closest below
            diff = today_price - trend_price
            if diff < min_prev_diff:
                min_prev_diff = diff
                previous_trend_line = line
                previous_trend_price = trend_price
                previous_trend_id = line.get("ID", None)

    # Check breakthrough status
    breakthrough = False
    if previous_trend_price is not None:
        yesterday_trend_price, _ = get_trend_line_price([previous_trend_line], today_date - pd.Timedelta(days=1))[0]
        breakthrough = yesterday_price < yesterday_trend_price and today_price > previous_trend_price

    # Calculate percentage differences
    prev_diff_percentage = (
        (today_price - previous_trend_price) / today_price * -100
        if previous_trend_price is not None
        else None
    )
    next_diff_percentage = (
        (next_trend_price - today_price) / today_price * 100
        if next_trend_price is not None
        else None
    )

    # Calculate trade days instead of calendar days
    def count_trade_days(df, date1, date2):
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values(by='time').reset_index(drop=True)
        index1 = df.index[df['time'] == pd.to_datetime(date1)].tolist()[0]
        index2 = df.index[df['time'] == pd.to_datetime(date2)].tolist()[0]
        trade_days = index2 - index1
        return trade_days

    previous_trend_period = (
        count_trade_days(data, previous_trend_line["End Date"], today_date)
        if previous_trend_line is not None and "End Date" in previous_trend_line
        else None
    )
    next_trend_period = (
        count_trade_days(data, next_trend_line["End Date"], today_date)
        if next_trend_line is not None and "End Date" in next_trend_line
        else None
    )

    # Check the last time the close price was above the "Next Trend Line ID"
    last_above_days = None
    if next_trend_id is not None:
        # Retrieve the start date for the trend line with the current Next Trend Line ID
        next_trend_line_start_date = pd.Timestamp(next_trend_line["Start Date"])
        for date, price in historical_close_prices[::-1]:
            if date < today_date and price > next_trend_price:
                last_above_days = (today_date - date).days
                break

    avg_volume = data.loc[data['time'] < today_date, 'volume'].mean()

    return {
        "Breakthrough": breakthrough,
        "Previous Trend Line Price": previous_trend_price,
        "Previous Trend Line (%)": prev_diff_percentage,
        "Previous Trend Line ID": previous_trend_id,
        "Previous Trend Line Period": previous_trend_period,  # Updated to trade days
        "Close Price": round(today_price, 2),
        "Next Trend Line Price": next_trend_price,
        "Next Trend Line (%)": next_diff_percentage,
        "Next Trend Line ID": next_trend_id,
        "Next Trend Line Period": next_trend_period,  # Updated to trade days
        "How Much Trend Lines Above": trend_lines_above,
        "Days Since Last Above Next Trend Line": last_above_days,
        "Volume": volume,
        "Average Volume": avg_volume,
    }


def ranked_trend_line(stock):
    try:
        trend_lines = pd.read_csv(f'alpha/trend_lines/{stock}.csv')
        trend_lines = trend_lines.sort_values(by='Start Price')
        trend_lines = trend_lines.sort_values(by=['Slope', 'Frequency'], ascending=[False, False])
        trend_lines = trend_lines.reset_index(drop=True)  # Reset index
        trend_lines['ID'] = trend_lines.index + 1
        trend_lines = trend_lines.sort_values(by=['Start Price', 'Slope'], ascending=[False, False])
        trend_lines['Rank'] = trend_lines.reset_index().index + 1
        return trend_lines
    except Exception as e:
        print(f'Error: {e}')
        return 0


def daily_close_against_trend_line(stock):
    trend_lines = ranked_trend_line(stock)
    try:
        trend_lines = trend_lines.to_dict('records')
    except:
        return 'Error. No trend line.'
    data = pd.read_csv(f'alpha/{stock}.csv')
    # trend_lines = trend_lines.drop(index=indexes_to_remove)
    data['time'] = pd.to_datetime(data['time'])
    results_list = []
    start_index = 1
    yesterday_price = data.loc[start_index-1, 'close']
    historical_close_prices = [(data.loc[start_index - 1, 'time'], yesterday_price)]

    for i in data.index[start_index:]:
        today_price = data.loc[i, 'close']
        today_date = data.loc[i, 'time']
        volume = data.loc[i, 'volume']
        results = analyze_price_breakthrough(data, yesterday_price, today_price, volume, today_date,
                                             trend_lines, historical_close_prices)
        results["Date"] = today_date
        results_list.append(results)

        historical_close_prices.append((today_date, today_price))
        yesterday_price = today_price

    results_df = pd.DataFrame(results_list)
    columns = ['Date'] + [col for col in results_df.columns if col != 'Date']
    results_df = results_df[columns]
    results_df.to_csv(f"alpha/samples/{stock}_breakthrough_analysis.csv", index=False)


def find_largest_negative_slope(data, nth_highest=1):
    """
    Find the nth highest price date (date1) and the date (date2) that creates the largest negative slope.

    Parameters:
    - data (list): A list of dictionaries containing 'Start Date', 'End Date', and prices.
    - nth_highest (int): The rank of the highest price to use as date1 (1 for highest, 2 for second highest, etc.).

    Returns:
    - tuple: A tuple containing (date1, date2, largest_slope) or None if no valid slope is found.
    """
    # Remove duplicates by Start Price and Start Date
    unique_data = []
    seen = set()
    for entry in data:
        identifier = (entry['Start Date'], entry['Start Price'])
        if identifier not in seen:
            seen.add(identifier)
            unique_data.append(entry)

    # Sort data by 'Start Price' in descending order and select the nth highest
    sorted_data = sorted(unique_data, key=lambda x: x['Start Price'], reverse=True)
    if nth_highest > len(sorted_data):
        return None  # Not enough entries to find the nth highest

    highest_price_entry = sorted_data[nth_highest - 1]
    date1 = datetime.strptime(highest_price_entry['Start Date'], '%Y-%m-%d')
    price1 = highest_price_entry['Start Price']
    log_y_start = np.log(price1)  # Log of the starting price

    largest_slope = float('-inf')  # Initialize with the smallest possible value
    best_date2 = None  # To store the best second date

    # Loop through all other dates
    for entry in data:
        date2 = datetime.strptime(entry['End Date'], '%Y-%m-%d')
        price2 = entry['End Price']

        # Ensure date2 is more recent than date1
        if date2 <= date1:
            continue

        # Calculate the slope in log scale
        x_start = date1.toordinal()
        x_end = date2.toordinal()
        log_y_end = np.log(price2)

        slope = (log_y_end - log_y_start) / (x_end - x_start)

        # Only consider negative slopes
        if slope >= 0:
            continue

        # Update the largest slope and corresponding date if a steeper slope is found
        if slope > largest_slope:
            largest_slope = slope
            best_date2 = entry['End Date']

    # Return the best pair and the largest slope
    return (highest_price_entry['Start Date'], best_date2, largest_slope) if best_date2 else None


def get_rsi_from_date(stock, start_date):
    # Alpha Vantage API URL
    api_key = "8LLD101ZZ48BBVC8"
    url = f"https://www.alphavantage.co/query?function=RSI&symbol={stock}&interval=daily&time_period=14&series_type=close&apikey={api_key}"

    # Request the data
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch RSI data for {stock}: {response.status_code}")

    # Parse the JSON response
    data = response.json()
    if "Technical Analysis: RSI" not in data:
        raise ValueError(f"RSI data not available for {stock}.")

    # Extract the RSI values
    rsi_data = data["Technical Analysis: RSI"]
    current_date = start_date[:10]
    start_date = datetime.strptime(current_date, "%Y-%m-%d")
    # Filter RSI values from the start date onward
    rsi_list = []
    for date_str, rsi_entry in rsi_data.items():
        rsi_date = datetime.strptime(date_str, "%Y-%m-%d")
        if rsi_date >= start_date:
            rsi_list.append(float(rsi_entry["RSI"]))
        else:
            break

    # Sort the list by date in ascending order
    return rsi_list[::-1]


def get_ema20_from_date(stock, start_date):
    # Alpha Vantage API URL
    api_key = "8LLD101ZZ48BBVC8"
    ema = 20
    url = f"https://www.alphavantage.co/query?function=EMA&symbol={stock}&interval=daily&time_period={ema}&series_type=close&apikey={api_key}"

    # Request the data
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch EMA20 data for {stock}: {response.status_code}")

    # Parse the JSON response
    data = response.json()
    if "Technical Analysis: EMA" not in data:
        raise ValueError(f"EMA20 data not available for {stock}.")

    # Extract the EMA values
    ema_data = data["Technical Analysis: EMA"]
    current_date = start_date[:10]
    start_date = datetime.strptime(current_date, "%Y-%m-%d")
    # Filter EMA values from the start date onward
    ema_list = []
    for date_str, ema_entry in ema_data.items():
        ema_date = datetime.strptime(date_str, "%Y-%m-%d")
        if ema_date >= start_date:
            ema_list.append(float(ema_entry["EMA"]))
        else:
            break

    # Sort the list by date in ascending order
    return ema_list[::-1]


def get_ma50_from_date(stock, start_date):
    # Alpha Vantage API URL
    api_key = "8LLD101ZZ48BBVC8"
    ma = 50
    url = f"https://www.alphavantage.co/query?function=SMA&symbol={stock}&interval=daily&time_period={ma}&series_type=close&apikey={api_key}"

    # Request the data
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch MA50 data for {stock}: {response.status_code}")

    # Parse the JSON response
    data = response.json()
    if "Technical Analysis: SMA" not in data:
        raise ValueError(f"MA50 data not available for {stock}.")

    # Extract the EMA values
    ma_data = data["Technical Analysis: SMA"]
    current_date = start_date[:10]
    start_date = datetime.strptime(current_date, "%Y-%m-%d")
    # Filter EMA values from the start date onward
    ma_list = []
    for date_str, ma_entry in ma_data.items():
        ma_date = datetime.strptime(date_str, "%Y-%m-%d")
        if ma_date >= start_date:
            ma_list.append(float(ma_entry["SMA"]))
        else:
            break

    # Sort the list by date in ascending order
    return ma_list[::-1]


def get_ma100_from_date(stock, start_date):
    # Alpha Vantage API URL
    api_key = "8LLD101ZZ48BBVC8"
    ma = 100
    url = f"https://www.alphavantage.co/query?function=SMA&symbol={stock}&interval=daily&time_period={ma}&series_type=close&apikey={api_key}"

    # Request the data
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch MA100 data for {stock}: {response.status_code}")

    # Parse the JSON response
    data = response.json()
    if "Technical Analysis: SMA" not in data:
        raise ValueError(f"MA100 data not available for {stock}.")

    # Extract the EMA values
    ma_data = data["Technical Analysis: SMA"]
    current_date = start_date[:10]
    start_date = datetime.strptime(current_date, "%Y-%m-%d")
    # Filter EMA values from the start date onward
    ma_list = []
    for date_str, ma_entry in ma_data.items():
        ma_date = datetime.strptime(date_str, "%Y-%m-%d")
        if ma_date >= start_date:
            ma_list.append(float(ma_entry["SMA"]))
        else:
            break

    # Sort the list by date in ascending order
    return ma_list[::-1]


def get_ma200_from_date(stock, start_date):
    # Alpha Vantage API URL
    api_key = "8LLD101ZZ48BBVC8"
    ma = 200
    url = f"https://www.alphavantage.co/query?function=SMA&symbol={stock}&interval=daily&time_period={ma}&series_type=close&apikey={api_key}"

    # Request the data
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch MA200 data for {stock}: {response.status_code}")

    # Parse the JSON response
    data = response.json()
    if "Technical Analysis: SMA" not in data:
        raise ValueError(f"MA200 data not available for {stock}.")

    # Extract the EMA values
    ma_data = data["Technical Analysis: SMA"]
    current_date = start_date[:10]
    start_date = datetime.strptime(current_date, "%Y-%m-%d")
    # Filter EMA values from the start date onward
    ma_list = []
    for date_str, ma_entry in ma_data.items():
        ma_date = datetime.strptime(date_str, "%Y-%m-%d")
        if ma_date >= start_date:
            ma_list.append(float(ma_entry["SMA"]))
        else:
            break

    # Sort the list by date in ascending order
    return ma_list[::-1]


def calculate_trendline_price(stock, date1, date2):
    input_file = f'alpha/{stock}.csv'
    data = pd.read_csv(input_file)

    # Extract unique trading dates and sort them
    trading_days = sorted(pd.to_datetime(data['time']).unique())

    # Convert dates to datetime
    date1 = pd.to_datetime(date1)
    date2 = pd.to_datetime(date2)
    # Ensure date1 is earlier than date2
    if date1 >= date2:
        raise ValueError("date1 must be earlier than date2")

    index1 = trading_days.index(date1)
    index2 = trading_days.index(date2)
    date_diff = index2 - index1

    trading_days_between = date_diff
    price1 = data.loc[index1, 'high']
    price2 = data.loc[index2, 'high']

    # Calculate log prices and slope in logarithmic scale
    log_price1 = np.log(price1)
    log_price2 = np.log(price2)
    log_slope = (log_price2 - log_price1) / trading_days_between

    date2 = date2.strftime('%Y-%m-%d')
    df = data[data['time'] >= date2].reset_index()
    trendline_prices = []
    duration_from_date1 = []
    duration_from_date2 = []
    rsi = get_rsi_from_date(stock, date2)
    ema20 = get_ema20_from_date(stock, date2)
    ma50 = get_ma50_from_date(stock, date2)
    ma100 = get_ma100_from_date(stock, date2)
    ma200 = get_ma200_from_date(stock, date2)

    for i in range(len(df)):
        current_date = pd.to_datetime(df.loc[i, 'time'])
        current_index = trading_days.index(current_date)

        # Calculate durations from date1 and date2
        duration_from_date1.append(current_index - index1)
        duration_from_date2.append(current_index - index2)
        additional_trading_days = i
        log_trend_price = log_price1 + log_slope * (trading_days_between + additional_trading_days)
        trend_price = np.exp(log_trend_price)
        trendline_prices.append(round(trend_price, 2))

    try:
        df['rsi'] = rsi
    except Exception as e:
        print(f'rsi error: {e}')

    try:
        df['ema20'] = ema20
    except Exception as e:
        print(f'ema20 error: {e}')

    try:
        df['ma50'] = ma50
    except Exception as e:
        print(f'ma50 error: {e}')

    try:
        df['ma100'] = ma100
    except Exception as e:
        print(f'ma100 error: {e}')

    try:
        df['ma200'] = ma200
    except Exception as e:
        print(f'ma200 error: {e}')

    df['trendline'] = trendline_prices
    df['duration_from_date1'] = duration_from_date1
    df['duration_from_date2'] = duration_from_date2
    df['distance'] = ((df['trendline'] - df['close']) / df['close']) * 100
    df['distance'] = df['distance'].round(2)
    df['breakthrough'] = df['high'] > df['trendline']
    try:
        if df.iloc[-1]['breakthrough']:
            save_breakthrough_row(df, 'daily_results.csv', stock)
            result = find_highest_price_and_validate_trendline(input_file)
            if result:
                results_file = 'trendlines.csv'
                save_trendline_result_to_csv(result, results_file, stock)
            else:
                print(f"No valid pair of dates found for {stock}")
                trendlines_to_update(stock)

    except Exception as e:
        print(f'Breakthrough? {e}', stock)
    df.to_csv(f"alpha/status/{stock}_status.csv", index=False)


def save_breakthrough_row(df, results_file, stock):
    # Extract the last row
    last_row = df.iloc[[-1]].copy()
    last_row['df_length'] = len(df) + 1
    last_row['stock'] = stock
    # Save to CSV, appending if the file already exists
    if not os.path.exists(results_file):
        last_row.to_csv(results_file, index=False)
    else:
        last_row.to_csv(results_file, mode='a', header=False, index=False)


def remove_duplicates_from_csv(input_file):
    # Read the CSV file
    df = pd.read_csv(input_file)

    # Remove duplicates
    df_cleaned = df.drop_duplicates()

    # Save the cleaned data to a new CSV file
    df_cleaned.to_csv(input_file, index=False)
    print(f"Duplicates removed. Cleaned data saved to {input_file}")


def save_trendline_result_to_csv(result, results_file, stock_name):
    if result:
        # Format the dates as strings in the format 'YYYY-MM-DD'
        date1_str = pd.to_datetime(result[0]).strftime('%Y-%m-%d')
        date2_str = pd.to_datetime(result[1]).strftime('%Y-%m-%d')

        # Create a DataFrame for the result
        result_df = pd.DataFrame([{
            'stock': stock_name,
            'date1': date1_str,
            'date2': date2_str,
            'slope': result[2]
        }])

        # Check if the results file exists
        if os.path.exists(results_file):
            # Load the existing data
            existing_df = pd.read_csv(results_file)

            # Check if the stock already exists in the DataFrame
            if stock_name in existing_df['stock'].values:
                # Update the existing row
                existing_df.loc[existing_df['stock'] == stock_name, ['date1', 'date2', 'slope']] = [date1_str,
                                                                                                    date2_str,
                                                                                                    result[2]]
            else:
                # Append the new row if the stock does not exist
                existing_df = pd.concat([existing_df, result_df], ignore_index=True)
        else:
            existing_df = result_df

        # Save the updated DataFrame to CSV
        existing_df.to_csv(results_file, index=False)


def trendlines_to_update(stock):
    input_file = 'trendlines_to_update.csv'
    result_df = pd.DataFrame([{
        'stock': stock,
    }])
    # Save to CSV, appending if the file already exists
    if not os.path.exists(input_file):
        result_df.to_csv(input_file, index=False)
    else:
        result_df.to_csv(input_file, mode='a', header=False, index=False)


def check_trendlines_to_update():
    try:
        data = pd.read_csv('trendlines_to_update.csv')
        for stock in data['stock']:
            input_file = f'alpha/{stock}.csv'
            result = find_highest_price_and_validate_trendline(input_file)
            if result:
                results_file = 'trendlines.csv'
                save_trendline_result_to_csv(result, results_file, stock)
                data = data[data['stock'] != stock]
        data.to_csv('trendlines_to_update.csv', index=False)
    except Exception as e:
        print(f'{e}')
        pass


def plot_chart(stock):
    """
    Plots the candlestick chart with high-to-high trendline and indicators,
    dynamically adjusting x-axis tick spacing and displaying price dots with labels on the y-axis.
    """
    # Paths and data
    stock_data_path = f'alpha/{stock}.csv'
    trendline_data_path = 'trendlines.csv'
    output_dir = 'alpha/plot'
    os.makedirs(output_dir, exist_ok=True)  # Ensure the output directory exists

    stock_data = pd.read_csv(stock_data_path)
    trendline_data = pd.read_csv(trendline_data_path)

    # Preprocess stock data
    stock_data['time'] = pd.to_datetime(stock_data['time'])
    stock_data.sort_values('time', inplace=True)

    # Filter trendline data for the given stock
    trendline = trendline_data[trendline_data['stock'] == stock]
    if trendline.empty:
        print(f"No trendline data available for {stock}.")
        return

    # Get trendline details
    date1 = pd.to_datetime(trendline['date1'].values[0])
    date2 = pd.to_datetime(trendline['date2'].values[0])

    # Handle missing dates by finding the nearest available dates
    def find_nearest_date(target_date):
        return stock_data.iloc[(stock_data['time'] - target_date).abs().argsort()[:1]]['time'].values[0]

    if date1 not in stock_data['time'].values:
        date1 = find_nearest_date(date1)
    if date2 not in stock_data['time'].values:
        date2 = find_nearest_date(date2)

    # Get high prices at the nearest dates
    high1 = stock_data.loc[stock_data['time'] == date1, 'high'].values[0]
    high2 = stock_data.loc[stock_data['time'] == date2, 'high'].values[0]

    # Calculate the start date (3 months before `date1`)
    start_date = date1 - pd.DateOffset(months=3)

    # Get indicator data
    ema20 = get_ema20_from_date(stock, str(start_date))
    ma50 = get_ma50_from_date(stock, str(start_date))
    ma100 = get_ma100_from_date(stock, str(start_date))
    ma200 = get_ma200_from_date(stock, str(start_date))

    # Filter stock data to only include the desired range
    filtered_data = stock_data[(stock_data['time'] >= start_date) & (stock_data['time'] <= stock_data['time'].max())]
    filtered_data.reset_index(drop=True, inplace=True)

    # Match the indicator data lengths to the filtered data
    min_length = len(filtered_data)
    ema20, ma50, ma100, ma200 = [data[:min_length] for data in [ema20, ma50, ma100, ma200]]

    # Calculate the slope dynamically using numerical dates
    date1_index = filtered_data.loc[filtered_data['time'] == date1].index[0]
    date2_index = filtered_data.loc[filtered_data['time'] == date2].index[0]
    slope = (high2 - high1) / (date2_index - date1_index)
    # Generate trendline points for the reindexed data
    trendline_prices = high1 + slope * (filtered_data.index - date1_index)

    # Determine dynamic x-axis tick spacing based on candle count
    candle_count = len(filtered_data)
    if candle_count < 100:
        buffer = 5
        tick_spacing = 1  # Show all dates
    elif candle_count < 500:
        buffer = 20
        tick_spacing = 5  # Every 5 days
    elif candle_count < 1000:
        buffer = 35
        tick_spacing = 10  # Every 10 days
    else:
        buffer = 50
        tick_spacing = 50  # Every 50 days

    # Plot candlestick chart
    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')

    # Plot candlesticks
    for _, row in filtered_data.iterrows():
        color = 'green' if row['close'] > row['open'] else 'red'
        ax.plot([row.name, row.name], [row['low'], row['high']], color='white', linewidth=0.8)  # Wick
        ax.plot([row.name, row.name], [row['open'], row['close']], color=color, linewidth=2)  # Body

    # Plot indicators
    ax.plot(filtered_data.index, ema20, label='EMA20', color='red', linewidth=1.5)
    ax.plot(filtered_data.index, ma50, label='MA50', color='orange', linewidth=1.5)
    ax.plot(filtered_data.index, ma100, label='MA100', color='green', linewidth=1.5)
    ax.plot(filtered_data.index, ma200, label='MA200', color='blue', linewidth=1.5)

    # Plot trendline
    ax.plot(filtered_data.index, trendline_prices, color='yellow', linewidth=2, label='High-to-High Trendline')

    # Add horizontal lines for indicator prices
    indicators = {
        'EMA20': (ema20[-1], 'red'),
        'MA50': (ma50[-1], 'orange'),
        'MA100': (ma100[-1], 'green'),
        'MA200': (ma200[-1], 'blue'),
        'Close': (filtered_data['close'].iloc[-1], 'white'),
    }

    rightmost_x = len(filtered_data) - 1 + buffer

    # Dictionary to track y-coordinates and their offsets to prevent overlap
    label_offsets = {}

    for label, (value, color) in indicators.items():
        y_coord = round(value, 2)  # Use rounded value as the key

        # Determine the vertical offset for this label
        if y_coord not in label_offsets:
            label_offsets[y_coord] = 0
        else:
            label_offsets[y_coord] += 10  # Add 10 units of vertical offset for stacking

        offset = label_offsets[y_coord]

        # Draw the horizontal line
        ax.plot([len(filtered_data) - 1, rightmost_x], [value, value], color=color, linestyle='--', linewidth=1.0)

        # Add the label with a vertical offset
        ax.text(
            rightmost_x + 0.5,
            value + offset,  # Apply vertical offset
            f"{label}: {value:.2f}",
            color=color,
            fontsize=10,
            va='center'
        )

    # Customize x-axis
    ax.set_xticks(filtered_data.index[::tick_spacing])  # Dynamic x-axis spacing
    ax.set_xticklabels(filtered_data['time'][::tick_spacing].dt.strftime('%Y-%m-%d'), rotation=90, color='white')
    ax.set_xlim([0, len(filtered_data) - 1 + buffer])
    # Customize y-axis
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.tick_params(axis='y', which='both', labelright=True, labelleft=False)
    plt.yticks(color='white')

    # Calculate dynamic y-axis limits
    highest_high = max(
        filtered_data['high'].max(),
        ema20[-1], ma50[-1], ma100[-1], ma200[-1], filtered_data['close'].iloc[-1]
    )
    lowest_low = min(
        filtered_data['low'].min(),
        ema20[-1], ma50[-1], ma100[-1], ma200[-1], filtered_data['close'].iloc[-1]
    )

    # Add a buffer (e.g., 5% of the range) to avoid clipping
    y_range_buffer = (highest_high - lowest_low) * 0.05
    y_min = lowest_low - y_range_buffer
    y_max = highest_high + y_range_buffer

    # Set y-axis limits
    ax.set_ylim([y_min, y_max])

    # Customize spines and grid
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('white')
    ax.spines['top'].set_color('white')
    ax.spines['right'].set_color('white')
    ax.grid(True, linestyle='--', alpha=0.6, color='gray')

    # Title and legend
    plt.title(f'{stock} - Trendline with Dynamic X Ticks and Indicator Labels', color='white')
    plt.legend(facecolor='black', edgecolor='white', loc='lower left', labelcolor='white',)
    plt.tight_layout()

    # Save the plot
    output_file = os.path.join(output_dir, f'{stock}_chart_with_dynamic_ticks.png')
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.show()


def create_trendline(stock):
    csv_path = f'alpha/{stock}.csv'
    stocks = pd.read_csv('trendlines.csv')
    stock_list = stocks['stock'].tolist()

    if stock not in stock_list:
        result = find_highest_price_and_validate_trendline(csv_path)
        results_file = 'trendlines.csv'
        save_trendline_result_to_csv(result, results_file, stock)
    else:
        return


def find_highest_price_and_validate_trendline(stock_file):
    # Load the CSV
    df = pd.read_csv(stock_file)

    # Ensure 'time' is in datetime format
    df['time'] = pd.to_datetime(df['time'])

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

    # Iterate through all rows after the highest point
    for index, row in sorted_df.iterrows():
        date2 = row['time']
        price2 = row['high']

        # Calculate the number of trading days between date1 and date2
        trading_days_between = len(df[(df['time'] >= date1) & (df['time'] <= date2)]) - 1
        if trading_days_between == 0:
            continue  # Avoid division by zero

        # Calculate the slope in log scale
        log_price1 = np.log(price1)
        log_price2 = np.log(price2)
        slope = (log_price2 - log_price1) / trading_days_between

        # Only consider negative slopes
        if slope >= 0 or round(slope, 7) < round(min_slope, 7):
            continue

        # Check that no high price between date1 and date2 is above the trendline
        is_valid = True
        for i, mid_row in df[(df['time'] > date1) & (df['time'] < date2)].iterrows():
            # Calculate the trendline price at mid_row using the trading day index
            trading_days_to_mid_row = len(df[(df['time'] >= date1) & (df['time'] <= mid_row['time'])]) - 1
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

    # Return the result if a valid pair is found
    if best_date2:
        return date1, best_date2, largest_negative_slope
    else:
        return None
    