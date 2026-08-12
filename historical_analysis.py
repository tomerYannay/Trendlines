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

import trendline_core as core

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

        dates = [r[0] for r in rows]
        highs = np.array([float(r[1]) for r in rows])

        result = core.best_upper_trendline(highs)
        if result is None:
            print(f"No valid trendline found for {stock} up to {last_date}.")
            return

        index1, index2, slope = result
        date1, date2 = dates[index1], dates[index2]
        date_diff = index2 - index1

        cursor.execute("""
            INSERT INTO upper_trendlines_historical (ticker, analysis_date, date1, date2, slope, date_diff, index2)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (stock, last_date, date1, date2, slope, date_diff, index2))
        connection.commit()

        print(f"Inserted historical upper trendline for {stock} (analysis_date: {last_date}): Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")

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

        dates = [r[0] for r in rows]
        highs = np.array([float(r[1]) for r in rows])

        result = core.best_upper_trendline(highs)
        if result is None:
            print(f"No valid trendline found for {stock} between {first_date} and {last_date}.")
            return

        index1, index2, slope = result
        date1, date2 = dates[index1], dates[index2]
        date_diff = index2 - index1

        cursor.execute("""
            INSERT INTO upper_trendlines_historical (ticker, analysis_date, date1, date2, slope, date_diff, index2)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (stock, last_date, date1, date2, slope, date_diff, index2))
        connection.commit()

        print(f"Inserted historical upper trendline for {stock} (analysis_date: {last_date}, first_date: {first_date}): Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")

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
    index_map = {d: i for i, d in enumerate(data['date'])}

    # Convert inputs to pandas Timestamps for consistent comparison
    date1 = pd.to_datetime(date1)
    date2 = pd.to_datetime(date2)
    target_date = pd.to_datetime(target_date)

    try:
        index1 = index_map[date1]
        index2 = index_map[date2]
        target_index = index_map[target_date]
    except KeyError as e:
        print(f"Date not found in trading days: {e}")
        return None

    price1 = float(data['high'].iloc[index1])
    price2 = float(data['high'].iloc[index2])

    log_slope = (np.log(price2) - np.log(price1)) / (index2 - index1)
    return core.trendline_price_at(target_index, index2, price2, log_slope)

@timed()
def calculate_sequence(breakthrough_series):
    """Calculate sequence of TRUE values in breakthrough column (vectorized)."""
    return core.calculate_sequence(breakthrough_series)

@timed()
def calculate_under_trendline_historical(data, date1, date2, target_date):
    """
    Calculate lower trendline prices using logarithmic scale for a specific target date.
    Returns only the trendline price for the target date.
    Uses LOW prices instead of HIGH for support line calculation.
    """
    index_map = {d: i for i, d in enumerate(data['date'])}

    # Convert inputs to pandas Timestamps for consistent comparison
    date1 = pd.to_datetime(date1)
    date2 = pd.to_datetime(date2)
    target_date = pd.to_datetime(target_date)

    try:
        index1 = index_map[date1]
        index2 = index_map[date2]
        target_index = index_map[target_date]
    except KeyError as e:
        print(f"Date not found in trading days: {e}")
        return None

    price1 = float(data['low'].iloc[index1])
    price2 = float(data['low'].iloc[index2])

    log_slope = (np.log(price2) - np.log(price1)) / (index2 - index1)
    return core.trendline_price_at(target_index, index2, price2, log_slope)

def _trendline_params(price_data, trading_days_map, date1, date2, price_col):
    """
    Resolve (index2, anchor_price, log_slope) for a stored trendline.
    Returns None when either anchor date is missing from the price series.
    """
    try:
        index1 = trading_days_map[pd.Timestamp(date1)]
        index2 = trading_days_map[pd.Timestamp(date2)]
    except KeyError:
        return None
    price1 = float(price_data[price_col].iloc[index1])
    price2 = float(price_data[price_col].iloc[index2])
    log_slope = (np.log(price2) - np.log(price1)) / (index2 - index1)
    return index1, index2, price2, log_slope


def _load_status_streak(cursor, table, stock):
    """
    Resume state for the running breakthrough streak: walk the tail of existing
    status rows. Returns (streak, previous_breakthrough).
    """
    cursor.execute(f"""
        SELECT breakthrough
        FROM {table}
        WHERE ticker = %s
        ORDER BY date;
    """, (stock,))
    flags = [row[0] for row in cursor.fetchall()]
    streak = 0
    for flag in reversed(flags):
        if flag:
            streak += 1
        else:
            break
    prev_bt = flags[-1] if flags else False
    return streak, prev_bt


@timed()
def update_upper_status_historical(stock):
    """
    Update upper_status_historical table using the correct historical trendline for each date.
    When update_trendline=True, calculates a new trendline and inserts into upper_trendlines_historical.

    Optimized: trendlines are cached in memory, the breakthrough streak is
    maintained as a running counter (no per-day queries), and status rows are
    inserted in a single batch.
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

        trading_days = list(price_data['date'])
        trading_days_map = {day: idx for idx, day in enumerate(trading_days)}
        closes = price_data['close'].values

        # Fetch existing entries to avoid duplicates
        cursor.execute("""
            SELECT date
            FROM upper_status_historical
            WHERE ticker = %s;
        """, (stock,))
        existing_dates = {row[0] for row in cursor.fetchall()}

        # Cache all historical trendlines for this ticker, ordered by analysis_date
        cursor.execute("""
            SELECT analysis_date, date1, date2
            FROM upper_trendlines_historical
            WHERE ticker = %s
            ORDER BY analysis_date;
        """, (stock,))
        trendlines = [(pd.Timestamp(r[0]), r[1], r[2]) for r in cursor.fetchall()]

        if not trendlines:
            print(f"No initial trendline data found for {stock}")
            return

        # Resume the running breakthrough streak from existing rows
        streak, prev_breakthrough = _load_status_streak(cursor, "upper_status_historical", stock)

        # Filter trading days to start from 2024-01-01
        start_date = pd.Timestamp('2024-01-01')
        filtered_trading_days = [d for d in trading_days if d >= start_date]

        tl_pointer = -1          # index into `trendlines` of the current line
        current_tl = None        # (analysis_date, date1, date2)
        tl_params = None         # (index1, index2, anchor_price, log_slope)
        insert_rows = []

        for current_date in filtered_trading_days:
            # Advance to the most recent trendline with analysis_date <= current_date
            while tl_pointer + 1 < len(trendlines) and trendlines[tl_pointer + 1][0] <= current_date:
                tl_pointer += 1
                current_tl = trendlines[tl_pointer]
                tl_params = _trendline_params(price_data, trading_days_map, current_tl[1], current_tl[2], 'high')

            if current_date.date() in existing_dates:
                continue  # Skip if already processed

            if current_tl is None or tl_params is None:
                continue

            index1, index2, anchor_price, log_slope = tl_params
            current_index = trading_days_map[current_date]

            trendline_price = core.trendline_price_at(current_index, index2, anchor_price, log_slope)
            close_price = float(closes[current_index])

            # Calculate metrics
            distance = ((trendline_price - close_price) / close_price) * 100
            breakthrough = close_price > trendline_price
            duration_from_date1 = current_index - index1
            duration_from_date2 = current_index - index2

            # Sequence: running streak of consecutive breakthroughs
            sequence_count = streak + 1 if breakthrough else 0

            update_trendline = (
                (sequence_count > 50) or
                ((distance > 0) and prev_breakthrough) or
                (distance < -20)
            )

            # If update_trendline is True, calculate and insert a new trendline
            if update_trendline:
                find_and_update_upper_trendline_historical(stock, current_date)

                cursor.execute("""
                    SELECT date1, date2
                    FROM upper_trendlines_historical
                    WHERE ticker = %s AND analysis_date = %s;
                """, (stock, current_date))
                new_trendline = cursor.fetchone()

                if new_trendline:
                    new_params = _trendline_params(price_data, trading_days_map, new_trendline[0], new_trendline[1], 'high')
                    if new_params is not None:
                        current_tl = (current_date, new_trendline[0], new_trendline[1])
                        tl_params = new_params
                        index1, index2, anchor_price, log_slope = tl_params
                        trendline_price = core.trendline_price_at(current_index, index2, anchor_price, log_slope)
                        distance = ((trendline_price - close_price) / close_price) * 100
                        breakthrough = close_price > trendline_price
                        duration_from_date1 = current_index - index1
                        duration_from_date2 = current_index - index2

            insert_rows.append((
                stock, current_date, float(trendline_price), float(distance), bool(breakthrough),
                int(duration_from_date1), int(duration_from_date2), int(sequence_count), bool(update_trendline)
            ))

            # Advance running state using the FINAL breakthrough value
            streak = streak + 1 if breakthrough else 0
            prev_breakthrough = breakthrough

        if insert_rows:
            execute_values(
                cursor,
                """
                INSERT INTO upper_status_historical (
                    ticker, date, trendline, distance, breakthrough,
                    duration_from_date1, duration_from_date2, sequence, update_trendline
                )
                VALUES %s;
                """,
                insert_rows
            )

        connection.commit()
        print(f"Updated upper_status_historical for {stock} ({len(insert_rows)} new rows)")

    except Exception as e:
        connection.rollback()
        raise e
    finally:
        cursor.close()
        connection.close()

@timed()
def update_under_status_historical(stock):
    """
    Update under_status_historical table using the correct historical trendline for each date.
    When update_trendline=True, calculates a new trendline and inserts into under_trendlines_historical.
    Uses LOW prices and support line logic (breakthrough when close < trendline).
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Fetch all stock prices for this ticker
        cursor.execute("""
            SELECT date, low, close
            FROM stock_prices
            WHERE ticker = %s
            ORDER BY date;
        """, (stock,))
        price_rows = cursor.fetchall()

        if not price_rows:
            print(f"No price data found for {stock}.")
            return

        price_data = pd.DataFrame(price_rows, columns=['date', 'low', 'close'])
        price_data['date'] = pd.to_datetime(price_data['date'])
        price_data['low'] = price_data['low'].astype(float)
        price_data['close'] = price_data['close'].astype(float)

        trading_days = list(price_data['date'])
        trading_days_map = {day: idx for idx, day in enumerate(trading_days)}
        closes = price_data['close'].values

        # Fetch existing entries to avoid duplicates
        cursor.execute("""
            SELECT date
            FROM under_status_historical
            WHERE ticker = %s;
        """, (stock,))
        existing_dates = {row[0] for row in cursor.fetchall()}

        # Cache all historical trendlines for this ticker, ordered by analysis_date
        cursor.execute("""
            SELECT analysis_date, date1, date2
            FROM under_trendlines_historical
            WHERE ticker = %s
            ORDER BY analysis_date;
        """, (stock,))
        trendlines = [(pd.Timestamp(r[0]), r[1], r[2]) for r in cursor.fetchall()]

        if not trendlines:
            print(f"No initial trendline data found for {stock}")
            return

        # Resume the running breakthrough streak from existing rows
        streak, prev_breakthrough = _load_status_streak(cursor, "under_status_historical", stock)

        # Filter trading days to start from 2024-01-01
        start_date = pd.Timestamp('2024-01-01')
        filtered_trading_days = [d for d in trading_days if d >= start_date]

        tl_pointer = -1
        current_tl = None
        tl_params = None
        insert_rows = []

        for current_date in filtered_trading_days:
            # Advance to the most recent trendline with analysis_date <= current_date
            while tl_pointer + 1 < len(trendlines) and trendlines[tl_pointer + 1][0] <= current_date:
                tl_pointer += 1
                current_tl = trendlines[tl_pointer]
                tl_params = _trendline_params(price_data, trading_days_map, current_tl[1], current_tl[2], 'low')

            if current_date.date() in existing_dates:
                continue  # Skip if already processed

            if current_tl is None or tl_params is None:
                continue

            index1, index2, anchor_price, log_slope = tl_params
            current_index = trading_days_map[current_date]

            trendline_price = core.trendline_price_at(current_index, index2, anchor_price, log_slope)
            close_price = float(closes[current_index])

            # Calculate metrics (OPPOSITE logic: breakthrough when close < trendline)
            distance = ((trendline_price - close_price) / close_price) * 100
            breakthrough = close_price < trendline_price
            duration_from_date1 = current_index - index1
            duration_from_date2 = current_index - index2

            # Sequence: running streak of consecutive breakthroughs
            sequence_count = streak + 1 if breakthrough else 0

            # Update condition adjusted for lower trendlines
            update_trendline = (
                (sequence_count > 50) or
                ((distance > 0) and prev_breakthrough) or
                (distance > 20)  # Changed from < -20 to > 20 for support lines
            )

            # If update_trendline is True, calculate and insert a new trendline
            if update_trendline:
                from db import find_and_update_under_trendline_historical
                find_and_update_under_trendline_historical(stock, current_date)

                cursor.execute("""
                    SELECT date1, date2
                    FROM under_trendlines_historical
                    WHERE ticker = %s AND analysis_date = %s;
                """, (stock, current_date))
                new_trendline = cursor.fetchone()

                if new_trendline:
                    new_params = _trendline_params(price_data, trading_days_map, new_trendline[0], new_trendline[1], 'low')
                    if new_params is not None:
                        current_tl = (current_date, new_trendline[0], new_trendline[1])
                        tl_params = new_params
                        index1, index2, anchor_price, log_slope = tl_params
                        trendline_price = core.trendline_price_at(current_index, index2, anchor_price, log_slope)
                        distance = ((trendline_price - close_price) / close_price) * 100
                        breakthrough = close_price < trendline_price
                        duration_from_date1 = current_index - index1
                        duration_from_date2 = current_index - index2

            insert_rows.append((
                stock, current_date, float(trendline_price), float(distance), bool(breakthrough),
                int(duration_from_date1), int(duration_from_date2), int(sequence_count), bool(update_trendline)
            ))

            # Advance running state using the FINAL breakthrough value
            streak = streak + 1 if breakthrough else 0
            prev_breakthrough = breakthrough

        if insert_rows:
            execute_values(
                cursor,
                """
                INSERT INTO under_status_historical (
                    ticker, date, trendline, distance, breakthrough,
                    duration_from_date1, duration_from_date2, sequence, update_trendline
                )
                VALUES %s;
                """,
                insert_rows
            )

        connection.commit()
        print(f"Updated under_status_historical for {stock} ({len(insert_rows)} new rows)")

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