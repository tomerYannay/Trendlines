import time
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import os
from psycopg2.extras import DictCursor
from datetime import datetime
from functools import wraps
from contextlib import contextmanager

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

# Database connection function
def get_db_connection():
    """Get a new database connection"""
    return psycopg2.connect(**db_config)

# === Simple profiler ===
PROFILE_ENABLED = True
PROFILE_ROWS = []

def _add_profile_row(scope, name, elapsed, ticker=None, extra=None):
    PROFILE_ROWS.append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "scope": scope,
        "name": name,
        "ticker": ticker or "",
        "elapsed_sec": round(elapsed, 4),
        "extra": extra or ""
    })

def timed(name=None, scope="function"):
    """
    Decorator for timing functions.
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
                ticker = None
                if args and isinstance(args[0], str) and args[0].isupper():
                    ticker = args[0]
                _add_profile_row(scope, label, t1 - t0, ticker=ticker)
        return wrapper
    return deco

@timed()
def find_and_update_upper_trendline_historical(stock, last_date):
    """
    Find the highest price and validate the trendline for a given stock up to a specific date.
    Similar to find_and_update_upper_trendline but with a last_date parameter that ensures
    date2 cannot be higher than this date. Used for historical trendline simulation.
    Inserts the result into upper_trendlines_historical table.
    """
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
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
        for _, row in sorted_df.iterrows():
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
            
    except Exception as e:
        connection.rollback()
        raise e
    finally:
        cursor.close()
        connection.close()

@timed()
def find_and_update_upper_trendline_historical_with_first_date(stock, first_date, last_date):
    """
    Find the highest price and validate the trendline for a given stock within a date range.
    Similar to find_and_update_upper_trendline_historical but with both first_date and last_date parameters.
    Ensures that date1 (the first peak) must be after first_date, and date2 must be before last_date.
    This creates a trendline where both points are within the specified range.
    Inserts the result into upper_trendlines_historical table.
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Convert dates to datetime for comparison
        if isinstance(first_date, str):
            first_date = pd.to_datetime(first_date)
        if isinstance(last_date, str):
            last_date = pd.to_datetime(last_date)

        # Fetch stock prices from the database within the date range
        cursor.execute("""
            SELECT date, high
            FROM stock_prices
            WHERE ticker = %s AND date >= %s AND date <= %s
            ORDER BY date;
        """, (stock, first_date, last_date))
        rows = cursor.fetchall()

        if not rows:
            print(f"No data found for {stock} between {first_date} and {last_date}.")
            return

        # Convert the data into a DataFrame
        df = pd.DataFrame(rows, columns=['time', 'high'])
        df['time'] = pd.to_datetime(df['time'])
        df['high'] = df['high'].astype(float)

        # Extract unique trading dates and sort them
        trading_days = sorted(df['time'].unique())

        # Find the highest price and its date (date1 must be >= first_date)
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
        for _, row in sorted_df.iterrows():
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

                print(f"Inserted historical upper trendline for {stock} (analysis_date: {last_date}, first_date: {first_date}): Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")
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

            print(f"Inserted historical upper trendline for {stock} (analysis_date: {last_date}, first_date: {first_date}): Date1: {date1}, Date2: {best_date2}, Slope: {largest_negative_slope}, Date_diff: {date_diff}, Index2: {index2}")
        else:
            print(f"No valid trendline found for {stock} between {first_date} and {last_date}.")

    except Exception as e:
        connection.rollback()
        raise e
    finally:
        cursor.close()
        connection.close()

@timed()
def calculate_upper_trendline_historical(data, date1, date2, target_date):
    """
    Calculate trendline prices using logarithmic scale for a specific target date.
    Returns only the trendline price for the target date.
    """
    trading_days = sorted(data['date'].unique())

    # Convert inputs to pandas Timestamps for consistent comparison
    date1 = pd.to_datetime(date1)
    date2 = pd.to_datetime(date2)
    target_date = pd.to_datetime(target_date)

    try:
        index1 = trading_days.index(date1)
        index2 = trading_days.index(date2)
        target_index = trading_days.index(target_date)
    except ValueError as e:
        print(f"Date not found in trading days: {e}")
        return None

    # Get high prices for date1 and date2
    price1 = float(data.loc[data['date'] == date1, 'high'].values[0])
    price2 = float(data.loc[data['date'] == date2, 'high'].values[0])

    # Calculate log prices and slope in logarithmic scale
    log_price1 = np.log(price1)
    log_price2 = np.log(price2)
    log_slope = (log_price2 - log_price1) / (index2 - index1)

    # Calculate trendline price for target date
    additional_trading_days = target_index - index2
    log_trend_price = log_price2 + log_slope * additional_trading_days
    trend_price = np.exp(log_trend_price)

    return round(trend_price, 2)

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
def update_upper_status_historical(stock):
    """
    Update upper_status_historical table using the correct historical trendline for each date.
    When update_trendline=True, calculates a new trendline and inserts into upper_trendlines_historical.
    """
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Fetch all stock prices for this ticker
        cursor.execute("""
            SELECT date, high, close
            FROM stock_prices
            WHERE ticker = %s
            ORDER BY date;
        """, (stock,))
        price_rows = cursor.fetchall()

        if not price_rows:
            print(f"No price data found for {stock}.")
            return

        price_data = pd.DataFrame(price_rows, columns=['date', 'high', 'close'])
        price_data['date'] = pd.to_datetime(price_data['date'])
        price_data['high'] = price_data['high'].astype(float)
        price_data['close'] = price_data['close'].astype(float)

        trading_days = sorted(price_data['date'].unique())
        trading_days_map = {day: idx for idx, day in enumerate(trading_days)}

        # Fetch existing entries to avoid duplicates
        cursor.execute("""
            SELECT date
            FROM upper_status_historical
            WHERE ticker = %s;
        """, (stock,))
        existing_dates = {row[0] for row in cursor.fetchall()}

        # Get the initial trendline (from 2024-01-01 or earliest available)
        cursor.execute("""
            SELECT date1, date2, slope, analysis_date
            FROM upper_trendlines_historical
            WHERE ticker = %s
            ORDER BY analysis_date
            LIMIT 1;
        """, (stock,))
        initial_trendline = cursor.fetchone()
        
        if not initial_trendline:
            print(f"No initial trendline data found for {stock}")
            return
            
        current_date1, current_date2, current_slope, _ = initial_trendline
        
        # Filter trading days to start from 2024-01-01
        start_date = pd.Timestamp('2024-01-01')
        filtered_trading_days = [d for d in trading_days if d >= start_date]
        
        # Process each trading day starting from 2024-01-01
        for current_date in filtered_trading_days:
            if current_date.date() in existing_dates:
                continue  # Skip if already processed

            # Get the most recent trendline that would be valid for this date
            cursor.execute("""
                SELECT date1, date2, slope, analysis_date
                FROM upper_trendlines_historical
                WHERE ticker = %s AND analysis_date <= %s
                ORDER BY analysis_date DESC
                LIMIT 1;
            """, (stock, current_date))
            
            trendline_data = cursor.fetchone()
            
            if not trendline_data:
                continue
                
            date1, date2, slope, _ = trendline_data
            
            # Calculate trendline price for current date
            trendline_price = calculate_upper_trendline_historical(price_data, date1, date2, current_date)
            
            if trendline_price is None:
                continue
                
            # Get current price data
            current_row = price_data[price_data['date'] == current_date].iloc[0]
            close_price = current_row['close']
            
            # Calculate metrics
            distance = ((trendline_price - close_price) / close_price) * 100
            breakthrough = close_price > trendline_price
            
            # Calculate durations
            try:
                index1 = trading_days_map[pd.Timestamp(date1)]
                index2 = trading_days_map[pd.Timestamp(date2)]
                current_index = trading_days_map[current_date]
                
                duration_from_date1 = current_index - index1
                duration_from_date2 = current_index - index2
            except KeyError:
                continue
                
            # For sequence calculation, we need to look at previous breakthroughs
            previous_dates = [d for d in filtered_trading_days if d < current_date]
            sequence_count = 0
            
            # Count consecutive breakthroughs leading up to current date
            for prev_date in reversed(previous_dates):
                cursor.execute("""
                    SELECT breakthrough
                    FROM upper_status_historical
                    WHERE ticker = %s AND date = %s;
                """, (stock, prev_date))
                prev_result = cursor.fetchone()
                
                if prev_result and prev_result[0]:  # If breakthrough was true
                    sequence_count += 1
                else:
                    break
                    
            # Add current breakthrough to sequence if true
            if breakthrough:
                sequence_count += 1
            else:
                sequence_count = 0
                
            # Calculate update_trendline condition
            previous_breakthrough = False
            if previous_dates:
                prev_date = previous_dates[-1]
                cursor.execute("""
                    SELECT breakthrough
                    FROM upper_status_historical
                    WHERE ticker = %s AND date = %s;
                """, (stock, prev_date))
                prev_result = cursor.fetchone()
                if prev_result:
                    previous_breakthrough = prev_result[0]
            
            update_trendline = (
                (sequence_count > 50) or
                ((distance > 0) and previous_breakthrough) or
                (distance < -20)
            )
            
            # If update_trendline is True, calculate and insert new trendline
            if update_trendline:
                # Calculate new trendline using data up to current_date
                find_and_update_upper_trendline_historical(stock, current_date)
                
                # Get the newly calculated trendline
                cursor.execute("""
                    SELECT date1, date2, slope
                    FROM upper_trendlines_historical
                    WHERE ticker = %s AND analysis_date = %s;
                """, (stock, current_date))
                new_trendline = cursor.fetchone()
                
                if new_trendline:
                    new_date1, new_date2, new_slope = new_trendline
                    # Recalculate trendline price with new trendline
                    trendline_price = calculate_upper_trendline_historical(price_data, new_date1, new_date2, current_date)
                    
                    if trendline_price is not None:
                        # Recalculate metrics with new trendline
                        distance = ((trendline_price - close_price) / close_price) * 100
                        breakthrough = close_price > trendline_price
                        
                        # Recalculate durations
                        try:
                            index1 = trading_days_map[pd.Timestamp(new_date1)]
                            index2 = trading_days_map[pd.Timestamp(new_date2)]
                            duration_from_date1 = current_index - index1
                            duration_from_date2 = current_index - index2
                        except KeyError:
                            pass
            
            # Insert into upper_status_historical
            # Convert numpy/pandas types to Python native types
            cursor.execute("""
                INSERT INTO upper_status_historical (
                    ticker, date, trendline, distance, breakthrough,
                    duration_from_date1, duration_from_date2, sequence, update_trendline
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                stock, current_date, float(trendline_price), float(distance), bool(breakthrough),
                int(duration_from_date1), int(duration_from_date2), int(sequence_count), bool(update_trendline)
            ))

        connection.commit()
        print(f"Updated upper_status_historical for {stock}")
        
    except Exception as e:
        connection.rollback()
        raise e
    finally:
        cursor.close()
        connection.close()

@timed()
def populate_historical_trendlines_for_date_range(stock, start_date, end_date):
    """
    Populate upper_trendlines_historical table for a range of dates.
    This calculates what the trendline would have been for each trading day in the range.
    """
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Convert dates to pandas timestamps
        start_date = pd.to_datetime(start_date)
        end_date = pd.to_datetime(end_date)
        
        # Get all trading days in the range
        cursor.execute("""
            SELECT DISTINCT date
            FROM stock_prices
            WHERE ticker = %s AND date >= %s AND date <= %s
            ORDER BY date;
        """, (stock, start_date, end_date))
        
        trading_days = [row[0] for row in cursor.fetchall()]
        
        print(f"Processing {len(trading_days)} trading days for {stock} from {start_date} to {end_date}")
        
        for trading_day in trading_days:
            # Check if we already have this analysis
            cursor.execute("""
                SELECT 1 FROM upper_trendlines_historical
                WHERE ticker = %s AND analysis_date = %s;
            """, (stock, trading_day))
            
            if cursor.fetchone():
                continue  # Skip if already exists
                
            # Calculate and insert historical trendline for this date
            find_and_update_upper_trendline_historical(stock, trading_day)
            
        print(f"Completed historical trendline population for {stock}")
        
    except Exception as e:
        connection.rollback()
        raise e
    finally:
        cursor.close()
        connection.close()

# Example usage functions
def example_usage():
    """
    Example of how to use the historical analysis functions
    """
    stock = "AAPL"
    
    # 1. Find and update upper trendline for specific date
    print("Step 1: Finding and updating upper trendline...")
    find_and_update_upper_trendline_historical(stock, '2024-01-01')
    
    # 2. Update historical status using the correct trendlines
    print("Step 2: Updating historical status...")
    update_upper_status_historical(stock)
    
    print("Historical analysis complete!")

@timed()
def update_ticker_extremes(ticker):
    """
    Calculate and update the MAX(high) and MIN(low) for a given ticker.
    Saves ticker, max_price, min_price, max_date, min_date to ticker_extremes table.
    Only updates if needed (new data exists or ticker not in table).
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Fetch the current extremes from ticker_extremes table if they exist
        cursor.execute("""
            SELECT max_price, min_price, max_date, min_date
            FROM ticker_extremes
            WHERE ticker = %s;
        """, (ticker,))
        existing_extremes = cursor.fetchone()

        # Fetch all stock prices for this ticker
        cursor.execute("""
            SELECT date, high, low
            FROM stock_prices
            WHERE ticker = %s
            ORDER BY date;
        """, (ticker,))
        price_rows = cursor.fetchall()

        if not price_rows:
            print(f"No price data found for {ticker}.")
            return

        # Convert to DataFrame for easier analysis
        df = pd.DataFrame(price_rows, columns=['date', 'high', 'low'])
        df['date'] = pd.to_datetime(df['date'])
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)

        # Find max high and min low
        max_row = df.loc[df['high'].idxmax()]
        min_row = df.loc[df['low'].idxmin()]

        max_price = float(max_row['high'])
        max_date = max_row['date']
        min_price = float(min_row['low'])
        min_date = min_row['date']

        # Check if update is needed
        if existing_extremes:
            existing_max_price, existing_min_price, existing_max_date, existing_min_date = existing_extremes

            # Only update if values have changed
            if (float(existing_max_price) == max_price and
                float(existing_min_price) == min_price and
                existing_max_date == max_date.date() and
                existing_min_date == min_date.date()):
                print(f"{ticker}: Extremes unchanged. No update needed.")
                return

            # Update existing record
            cursor.execute("""
                UPDATE ticker_extremes
                SET max_price = %s,
                    min_price = %s,
                    max_date = %s,
                    min_date = %s,
                    last_updated = CURRENT_TIMESTAMP
                WHERE ticker = %s;
            """, (max_price, min_price, max_date, min_date, ticker))
            print(f"Updated extremes for {ticker}: MAX={max_price} on {max_date.date()}, MIN={min_price} on {min_date.date()}")
        else:
            # Insert new record
            cursor.execute("""
                INSERT INTO ticker_extremes (ticker, max_price, min_price, max_date, min_date)
                VALUES (%s, %s, %s, %s, %s);
            """, (ticker, max_price, min_price, max_date, min_date))
            print(f"Inserted extremes for {ticker}: MAX={max_price} on {max_date.date()}, MIN={min_price} on {min_date.date()}")

        connection.commit()

    except Exception as e:
        connection.rollback()
        raise e
    finally:
        cursor.close()
        connection.close()


@timed()
def update_all_ticker_extremes():
    """
    Update extremes for all tickers in the tickers table.
    This function processes all tickers and updates their max/min prices.
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Fetch all tickers from the tickers table
        cursor.execute("SELECT ticker FROM tickers ORDER BY ticker;")
        tickers = [row[0] for row in cursor.fetchall()]

        if not tickers:
            print("No tickers found in tickers table.")
            return

        print(f"Processing {len(tickers)} tickers for extreme price updates...")

        for ticker in tickers:
            try:
                update_ticker_extremes(ticker)
            except Exception as e:
                print(f"Error processing {ticker}: {e}")
                continue

        print(f"Completed extreme price updates for all tickers.")

    except Exception as e:
        print(f"Error fetching tickers: {e}")
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    # Run example
    example_usage()