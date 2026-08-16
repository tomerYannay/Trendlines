import re
import time
import threading
import numpy as np
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from psycopg2.extras import execute_values
import pandas as pd
import psycopg2
from dotenv import load_dotenv
import os
from psycopg2.extras import DictCursor

import trendline_core as core

# Load environment variables from the .env file
load_dotenv()

# Alpha Vantage configuration — key must live in .env, never in code
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY')
ALPHA_VANTAGE_RPM = int(os.getenv('ALPHA_VANTAGE_RPM', '75'))  # calls per minute, match your plan tier


def _resolve_api_key(prem_key=None):
    key = prem_key or ALPHA_VANTAGE_KEY
    if not key:
        raise ValueError("Alpha Vantage API key missing. Set ALPHA_VANTAGE_KEY in .env")
    return key


class _RateLimiter:
    """Thread-safe limiter that spaces API calls to `calls_per_minute`."""

    def __init__(self, calls_per_minute):
        self.interval = 60.0 / max(1, calls_per_minute)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            time.sleep(delay)


_api_rate_limiter = _RateLimiter(ALPHA_VANTAGE_RPM)

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
        # never persist the API key in profiling output
        safe_url = re.sub(r'apikey=[^&]*', 'apikey=***', url)
        _add_profile_row(scope, name or url.split("function=")[-1][:40], t1 - t0, ticker=ticker, extra=safe_url)
    return resp

@timed()
def fetch_latest_global_quote(symbol, prem_key=None, retry_delay=31):
    """
    Fetch only the latest day's OHLCV using Alpha Vantage GLOBAL_QUOTE.
    Implements rate limit detection and automatic retry with configurable delay.
    """
    prem_key = _resolve_api_key(prem_key)
    url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={prem_key}'
    _api_rate_limiter.wait()

    max_retries = 3
    for attempt in range(max_retries):
        r = http_get_timed(url, scope="api", name="GLOBAL_QUOTE", ticker=symbol)

        if r.status_code != 200:
            raise ConnectionError(f"Failed to fetch GLOBAL_QUOTE for {symbol}: {r.status_code}")

        data = r.json()

        # Check for rate limit message
        if "Information" in data:
            if "higher API call volume" in data["Information"] or "call frequency" in data["Information"]:
                if attempt < max_retries - 1:
                    print(f"⚠️ Rate limit hit for {symbol}. Waiting {retry_delay} seconds before retry (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise ValueError(f"Rate limit exceeded for {symbol} after {max_retries} attempts: {data}")

        # Check for valid response
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

    raise ValueError(f"Failed to fetch data for {symbol} after {max_retries} attempts")



@timed()
def fetchDailyJson(symbol, prem_key=None):
    """
    Fetch daily stock data for the given symbol using Alpha Vantage API.
    """
    prem_key = _resolve_api_key(prem_key)
    api_url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize=compact&apikey={prem_key}'
    _api_rate_limiter.wait()
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
def add_close_high_low_open(symbol, prem_key=None):
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


def _fetch_daily_adjusted_df(symbol, outputsize='full', adjust='split', prem_key=None):
    """
    Fetch DAILY_ADJUSTED data from Alpha Vantage as a DataFrame indexed by date.
    Keeps the split_coef column so callers can detect split events.

    Parameters:
        symbol: Stock ticker symbol
        outputsize: 'full' (entire history) or 'compact' (last ~100 trading days)
        adjust: Adjustment mode
          - 'none'  -> raw O/H/L/C as returned in fields 1..4
          - 'alpha' -> adjust O/H/L using factor = adj_close / close (Alpha's adjusted close)
          - 'split' -> adjust O/H/L using cumulative split coefficients only (closest to IBKR)
    """
    prem_key = _resolve_api_key(prem_key)
    api_url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize={outputsize}&apikey={prem_key}'
    _api_rate_limiter.wait()

    response = http_get_timed(api_url, scope="api", name="TIME_SERIES_DAILY_ADJUSTED", ticker=symbol)

    if response.status_code != 200:
        raise ConnectionError(f"Failed to fetch data for {symbol}: {response.status_code}")

    data = response.json()

    if "Time Series (Daily)" not in data:
        raise ValueError(f"Error in API response for {symbol}: {data}")

    time_series = data["Time Series (Daily)"]

    # Build DataFrame from API response
    df = pd.DataFrame.from_dict(time_series, orient='index')
    df.index = pd.to_datetime(df.index)
    df = df.rename(columns={
        '1. open': 'open',
        '2. high': 'high',
        '3. low': 'low',
        '4. close': 'close',
        '5. adjusted close': 'adj_close',
        '6. volume': 'volume',
        '7. dividend amount': 'dividend',
        '8. split coefficient': 'split_coef'
    })[['open', 'high', 'low', 'close', 'adj_close', 'volume', 'dividend', 'split_coef']].sort_index()

    # Convert types
    for col in ['open', 'high', 'low', 'close', 'adj_close', 'dividend', 'split_coef']:
        df[col] = df[col].astype(float)
    df['volume'] = df['volume'].astype(int)

    if adjust == 'none':
        # Return RAW prices - no adjustment
        pass

    elif adjust == 'alpha':
        # Adjust using factor = adj_close / close (includes dividends if present)
        factor = (df['adj_close'] / df['close']).replace([pd.NA, pd.NaT], 1).fillna(1)
        df['open'] = (df['open'] * factor).round(6)
        df['high'] = (df['high'] * factor).round(6)
        df['low'] = (df['low'] * factor).round(6)
        df['close'] = df['adj_close'].round(6)

    elif adjust == 'split':
        # Adjust for splits only using cumulative split coefficients
        # Alpha returns split_coef=3.0, 5.0 on split days; multiply all *past* prices by this factor
        cum_split = df['split_coef'].replace(0, 1.0).fillna(1.0)
        # Reverse cumulative product to adjust historical prices to today's units
        cum_split = cum_split.iloc[::-1].cumprod().iloc[::-1]
        factor = (1.0 / cum_split).fillna(1.0)

        df['open'] = (df['open'] * factor).round(6)
        df['high'] = (df['high'] * factor).round(6)
        df['low'] = (df['low'] * factor).round(6)
        df['close'] = (df['close'] * factor).round(6)

    else:
        raise ValueError("adjust must be one of: 'none', 'alpha', 'split'")

    return df


def _df_to_price_rows(symbol, df):
    """Convert a fetched DataFrame to (symbol, date, o, h, l, c, v) insert tuples."""
    return [
        (symbol, d.strftime('%Y-%m-%d'),
         float(round(row.open, 4)), float(round(row.high, 4)), float(round(row.low, 4)),
         float(round(row.close, 4)), int(row.volume))
        for d, row in df.iterrows()
    ]


@timed()
def fetch_full_historical_data(symbol, prem_key=None, adjust='split'):
    """
    Fetch full DAILY_ADJUSTED history from Alpha Vantage and return rows:
    (symbol, date, open, high, low, close, volume)
    """
    df = _fetch_daily_adjusted_df(symbol, outputsize='full', adjust=adjust, prem_key=prem_key)
    return _df_to_price_rows(symbol, df)


@timed()
def prefetch_daily_data(symbols, outputsize='compact', adjust='split', max_workers=8, prem_key=None):
    """
    Fetch daily data for many symbols in parallel (thread pool + shared rate limiter).
    Returns {symbol: DataFrame} — failed symbols are omitted (and logged).
    The rate limiter keeps total request rate within ALPHA_VANTAGE_RPM regardless
    of max_workers, so this is safe for any Alpha Vantage plan tier.
    """
    results = {}
    errors = 0

    def _one(sym):
        return sym, _fetch_daily_adjusted_df(sym, outputsize=outputsize, adjust=adjust, prem_key=prem_key)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_one, s) for s in symbols]
        for fut in as_completed(futures):
            try:
                sym, df = fut.result()
                results[sym] = df
            except Exception as e:
                errors += 1
                print(f"⚠️ Prefetch failed: {e}")

    print(f"📥 Prefetched {len(results)}/{len(symbols)} symbols ({errors} errors)")
    return results


def _reload_history_after_split(symbol, prem_key=None):
    """
    A split was detected in newly fetched data: the entire price history in the
    DB is in the old (pre-split) scale and must be replaced with split-adjusted
    history. Also clears the status tables (their stored trendline prices are in
    the old scale) and re-anchors the trendlines so everything is recomputed
    consistently on the next status update.
    """
    print(f"🔀 {symbol}: split detected — reloading full split-adjusted history")
    rows = fetch_full_historical_data(symbol, prem_key=prem_key)
    if not rows:
        raise ValueError(f"{symbol}: split refetch returned no data")

    cursor.execute("DELETE FROM stock_prices WHERE ticker = %s;", (symbol,))
    execute_values(
        cursor,
        """
        INSERT INTO stock_prices (ticker, date, open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (ticker, date) DO NOTHING;
        """,
        rows
    )

    # Stored status rows hold trendline prices in the old scale — clear so they rebuild
    for status_table in ("upper_status", "under_status"):
        try:
            cursor.execute(f"DELETE FROM {status_table} WHERE ticker = %s;", (symbol,))
        except Exception:
            connection.rollback()
    connection.commit()

    # Re-anchor trendlines on the adjusted history
    cursor.execute("SELECT 1 FROM upper_trendlines WHERE ticker = %s;", (symbol,))
    if cursor.fetchone():
        find_and_update_upper_trendline(symbol)
    cursor.execute("SELECT 1 FROM under_trendlines WHERE ticker = %s;", (symbol,))
    if cursor.fetchone():
        find_and_update_under_trendline(symbol)

    # Keep ticker extremes in sync with the new scale
    try:
        from historical_analysis import update_ticker_extremes
        update_ticker_extremes(symbol)
    except Exception as e:
        print(f"⚠️ {symbol}: could not refresh ticker_extremes after split: {e}")


@timed()
def updateDBWithAPI(symbol, prem_key=None, prefetched_df=None):
    """
    Update database with stock prices from last date in DB to today.
    - New ticker: fetch and insert full split-adjusted history.
    - Existing ticker: incremental update from a compact fetch (last ~100 days);
      falls back to a full fetch when the gap is larger than the compact window.
    - Split day detected among the new rows: reload the entire history so past
      prices are re-adjusted to the new scale.
    Returns (inserted_dates_list, is_new_ticker_boolean).

    prefetched_df: optional DataFrame from prefetch_daily_data() to avoid a
    second API call when data was already fetched in parallel.
    """
    cursor.execute("SELECT MAX(date) FROM stock_prices WHERE ticker = %s;", (symbol,))
    latest_date_in_db = cursor.fetchone()[0]  # date or None

    # If no data exists for this ticker, fetch full historical data
    if latest_date_in_db is None:
        print(f"{symbol}: No existing data found. Fetching full historical data...")
        try:
            rows = fetch_full_historical_data(symbol, prem_key=prem_key)
            if rows:
                execute_values(
                    cursor,
                    """
                    INSERT INTO stock_prices (ticker, date, open, high, low, close, volume)
                    VALUES %s
                    ON CONFLICT (ticker, date) DO NOTHING;
                    """,
                    rows
                )
                connection.commit()
                inserted_dates = [row[1] for row in rows]
                print(f"Inserted {len(rows)} historical records for {symbol}")
                return inserted_dates, True  # True indicates this is a new ticker
            else:
                print(f"{symbol}: No historical data available.")
                return [], True
        except Exception as e:
            print(f"Failed to fetch full historical data for {symbol}: {e}")
            connection.rollback()  # Rollback the failed transaction
            return [], True

    # Ticker exists — incremental update from compact data
    try:
        df = prefetched_df if prefetched_df is not None else _fetch_daily_adjusted_df(symbol, outputsize='compact', prem_key=prem_key)

        if df.empty:
            print(f"{symbol}: No data available from API.")
            return [], False

        latest_ts = pd.Timestamp(latest_date_in_db)

        # Gap larger than the compact window (~100 trading days) → need full history
        if df.index.min() > latest_ts:
            df = _fetch_daily_adjusted_df(symbol, outputsize='full', prem_key=prem_key)

        new_df = df[df.index > latest_ts]

        if new_df.empty:
            print(f"{symbol}: DB already up-to-date through {latest_date_in_db}.")
            return [], False

        inserted_dates = [d.strftime('%Y-%m-%d') for d in new_df.index]

        # Split among the new rows → all stored history is in the old scale
        if (new_df['split_coef'].fillna(1.0) != 1.0).any():
            _reload_history_after_split(symbol, prem_key=prem_key)
            return inserted_dates, False

        new_rows = _df_to_price_rows(symbol, new_df)
        execute_values(
            cursor,
            """
            INSERT INTO stock_prices (ticker, date, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (ticker, date) DO NOTHING;
            """,
            new_rows
        )
        connection.commit()
        print(f"Inserted {len(new_rows)} new records for {symbol} (through {inserted_dates[-1]})")
        return inserted_dates, False

    except Exception as e:
        print(f"Failed to update {symbol}: {e}")
        connection.rollback()  # Rollback the failed transaction
        return [], False



def _locate_index(index_map, d):
    """Locate a date in a {date: index} map, tolerating date/Timestamp mismatches."""
    if d in index_map:
        return index_map[d]
    ts = pd.Timestamp(d)
    if ts in index_map:
        return index_map[ts]
    return index_map[ts.date()]


@timed()
def update_upper_status(stock):
    """
    Update the upper_status table for a given stock.
    Fully vectorized; new rows are inserted in a single batch.
    """

    # Fetch trendline data from upper_trendlines
    cursor.execute("""
        SELECT date1, date2, slope
        FROM upper_trendlines
        WHERE ticker = %s;
    """, (stock,))
    trendline_data = cursor.fetchone()

    if not trendline_data:
        # Self-heal: anchor a trendline instead of failing (new ticker / cleared table)
        find_and_update_upper_trendline(stock)
        cursor.execute("""
            SELECT date1, date2, slope
            FROM upper_trendlines
            WHERE ticker = %s;
        """, (stock,))
        trendline_data = cursor.fetchone()
        if not trendline_data:
            # Legitimate: a stock at its all-time high has no descending diagonal
            # (no later high to anchor to). Status will populate once one forms.
            print(f"ℹ️ {stock}: no upper trendline possible (at all-time high) — skipping status")
            return

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

    n = len(data)
    index_map = {d: i for i, d in enumerate(data['date'])}
    index1 = _locate_index(index_map, date1)
    index2 = _locate_index(index_map, date2)

    # Calculate the required values (vectorized)
    data['trendline'] = calculate_upper_trendline(data, date1, date2, index_map=index_map)
    data['distance'] = ((data['trendline'].astype(float) - data['close']) / data['close']) * 100
    data['breakthrough'] = data['close'] > data['trendline']
    data['duration_from_date1'] = np.arange(n) - index1
    data['duration_from_date2'] = np.arange(n) - index2
    data['sequence'] = calculate_sequence(data['breakthrough'])

    # Renewal rules — validated head-to-head over 2022-2026 (research/compare_renewal_rules.py):
    # persistent lines (200d / 100% / deep-failure-only) preserve the repeat-attempt edge.
    # Deep failure: once the line has been broken (any close above it), ANY later close
    # more than 5% below it resets the diagonal — not only the day right after a breakout.
    had_breakout = data['breakthrough'].cummax()
    data['update_trendline'] = (
            (data['sequence'] > 200) |
            (had_breakout & (data['distance'] > 5)) |
            (data['distance'] < -100)
    )

    # Fetch existing entries in the upper_status table for the given ticker
    cursor.execute("""
        SELECT date
        FROM upper_status
        WHERE ticker = %s;
    """, (stock,))
    existing_dates = {row[0] for row in cursor.fetchall()}

    missing = data[~data['date'].isin(existing_dates)]
    if missing.empty:
        connection.commit()
        print(f"Updated upper_status for {stock} (no new dates)")
        return

    # Fetch last update_all_lines date
    cursor.execute("""
        SELECT MAX(update_all_lines)
        FROM upper_status
        WHERE ticker = %s AND update_all_lines IS NOT NULL;
    """, (stock,))
    last_update_date = cursor.fetchone()[0]

    called_update_all = False
    insert_rows = []
    for _, row in missing.iterrows():
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

        insert_rows.append((
            stock, row['date'], float(row['trendline']), float(row['distance']), bool(row['breakthrough']),
            int(row['duration_from_date1']), int(row['duration_from_date2']), int(row['sequence']),
            bool(row['update_trendline']), update_all_lines_date
        ))

    execute_values(
        cursor,
        """
        INSERT INTO upper_status (ticker, date, trendline, distance, breakthrough, duration_from_date1,
        duration_from_date2, sequence, update_trendline, update_all_lines)
        VALUES %s;
        """,
        insert_rows
    )

    connection.commit()
    print(f"Updated upper_status for {stock} ({len(insert_rows)} new rows)")

@timed()
def calculate_upper_trendline(data, date1, date2, index_map=None):
    """
    Calculate trendline prices using logarithmic scale (vectorized).
    data must be ordered by date with one row per trading day.
    """
    if index_map is None:
        index_map = {d: i for i, d in enumerate(data['date'])}
    index1 = _locate_index(index_map, date1)
    index2 = _locate_index(index_map, date2)

    price1 = float(data['high'].iloc[index1])
    price2 = float(data['high'].iloc[index2])

    log_slope = (np.log(price2) - np.log(price1)) / (index2 - index1)
    return core.trendline_prices(len(data), index2, price2, log_slope)

@timed()
def update_under_status(stock):
    """
    Update the under_status table for a given stock.
    Fully vectorized; new rows are inserted in a single batch.
    """

    # Fetch trendline data from under_trendlines
    cursor.execute("""
        SELECT date1, date2, slope
        FROM under_trendlines
        WHERE ticker = %s;
    """, (stock,))
    trendline_data = cursor.fetchone()

    if not trendline_data:
        # Self-heal: anchor a trendline instead of failing (new ticker / cleared table)
        find_and_update_under_trendline(stock)
        cursor.execute("""
            SELECT date1, date2, slope
            FROM under_trendlines
            WHERE ticker = %s;
        """, (stock,))
        trendline_data = cursor.fetchone()
        if not trendline_data:
            # Legitimate: a stock at its all-time low has no ascending support line
            print(f"ℹ️ {stock}: no under trendline possible (at all-time low) — skipping status")
            return

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

    n = len(data)
    index_map = {d: i for i, d in enumerate(data['date'])}
    index1 = _locate_index(index_map, date1)
    index2 = _locate_index(index_map, date2)

    # Calculate the required values (vectorized)
    data['trendline'] = calculate_under_trendline(data, date1, date2, index_map=index_map)
    data['distance'] = ((data['trendline'].astype(float) - data['close']) / data['close']) * 100
    data['breakthrough'] = data['close'] < data['trendline']
    data['duration_from_date1'] = np.arange(n) - index1
    data['duration_from_date2'] = np.arange(n) - index2
    data['sequence'] = calculate_sequence(data['breakthrough'])

    # Add a column for `update_trendline` based on the conditions
    previous_breakthrough = data['breakthrough'].shift(1, fill_value=False)
    data['update_trendline'] = (
            (data['sequence'] > 50) |
            ((data['distance'] > 0) & previous_breakthrough) |
            (data['distance'] > 20)
    )

    # Fetch existing entries in the under_status table for the given ticker
    cursor.execute("""
        SELECT date
        FROM under_status
        WHERE ticker = %s;
    """, (stock,))
    existing_dates = {row[0] for row in cursor.fetchall()}

    missing = data[~data['date'].isin(existing_dates)]
    if not missing.empty:
        insert_rows = [
            (
                stock, row['date'], float(row['trendline']), float(row['distance']), bool(row['breakthrough']),
                int(row['duration_from_date1']), int(row['duration_from_date2']), int(row['sequence']),
                bool(row['update_trendline'])
            )
            for _, row in missing.iterrows()
        ]
        execute_values(
            cursor,
            """
            INSERT INTO under_status (ticker, date, trendline, distance, breakthrough, duration_from_date1,
            duration_from_date2, sequence, update_trendline)
            VALUES %s;
            """,
            insert_rows
        )

    connection.commit()
    print(f"Updated under_status for {stock} ({len(missing)} new rows)")

@timed()
def calculate_under_trendline(data, date1, date2, index_map=None):
    """
    Calculate under trendline prices using logarithmic scale (vectorized).
    data must be ordered by date with one row per trading day.
    """
    if index_map is None:
        index_map = {d: i for i, d in enumerate(data['date'])}
    index1 = _locate_index(index_map, date1)
    index2 = _locate_index(index_map, date2)

    price1 = float(data['low'].iloc[index1])
    price2 = float(data['low'].iloc[index2])

    log_slope = (np.log(price2) - np.log(price1)) / (index2 - index1)
    return core.trendline_prices(len(data), index2, price2, log_slope)

@timed()
def calculate_sequence(breakthrough_series):
    """Calculate sequence of TRUE values in breakthrough column (vectorized)."""
    return core.calculate_sequence(breakthrough_series)

@timed()
def find_and_update_upper_trendline(stock):
    """
    Find the upper trendline for a given stock (vectorized, O(n)) and upsert it
    into the upper_trendlines table, including date_diff and index2.
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

    dates = [r[0] for r in rows]
    highs = np.array([float(r[1]) for r in rows])

    result = core.best_upper_trendline(highs)
    if result is None:
        print(f"No valid trendline found for {stock}.")
        return

    index1, index2, slope = result
    date1, date2 = dates[index1], dates[index2]
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
    """, (stock, date1, date2, slope, date_diff, index2))
    connection.commit()

    print(f"Updated upper_trendlines for {stock}: Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")

@timed()
def find_and_update_upper_trendline_historical(stock, last_date):
    """
    Find the upper trendline for a given stock using only data up to last_date
    (vectorized). Used for historical trendline simulation.
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

@timed()
def find_and_update_under_trendline_historical(stock, last_date):
    """
    Find the under (support) trendline for a given stock using only data up to
    last_date (vectorized). Used for historical trendline simulation.
    Inserts the result into under_trendlines_historical table.
    """

    # Convert last_date to datetime for comparison
    if isinstance(last_date, str):
        last_date = pd.to_datetime(last_date)

    # Fetch stock prices from the database up to last_date
    cursor.execute("""
        SELECT date, low
        FROM stock_prices
        WHERE ticker = %s AND date <= %s
        ORDER BY date;
    """, (stock, last_date))
    rows = cursor.fetchall()

    if not rows:
        print(f"No data found for {stock} up to {last_date}.")
        return

    dates = [r[0] for r in rows]
    lows = np.array([float(r[1]) for r in rows])

    result = core.best_under_trendline(lows)
    if result is None:
        print(f"No valid trendline found for {stock} up to {last_date}.")
        return

    index1, index2, slope = result
    date1, date2 = dates[index1], dates[index2]
    date_diff = index2 - index1

    cursor.execute("""
        INSERT INTO under_trendlines_historical (ticker, analysis_date, date1, date2, slope, date_diff, index2)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
    """, (stock, last_date, date1, date2, slope, date_diff, index2))
    connection.commit()

    print(f"Inserted historical lower trendline for {stock} (analysis_date: {last_date}): Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")

@timed()
def check_and_update_upper_trendline(stock, updated_dates):
    """
    Re-anchor the upper trendline when any of the newly inserted dates is
    flagged update_trendline=TRUE and is newer than the current anchor (date2).
    Single query over all updated dates.
    """
    if not updated_dates:
        return

    cursor.execute("""
        SELECT MAX(date)
        FROM upper_status
        WHERE ticker = %s AND update_trendline = TRUE AND date = ANY(%s::date[]);
    """, (stock, list(updated_dates)))
    last_update_trendline_date = cursor.fetchone()[0]

    if not last_update_trendline_date:
        return

    # Fetch the current date2 from upper_trendlines
    cursor.execute("""
        SELECT date2
        FROM upper_trendlines
        WHERE ticker = %s;
    """, (stock,))
    result = cursor.fetchone()

    if not result:
        raise ValueError(f"No trendline data found for {stock} in upper_trendlines.")

    if last_update_trendline_date > result[0]:
        print(f"Triggering trendline update for {stock}.")
        find_and_update_upper_trendline(stock)

@timed()
def find_and_update_under_trendline(stock):
    """
    Find the under (support) trendline for a given stock (vectorized, O(n)).
    Update the under_trendlines table with new trendline data, including
    date_diff and index2. If the ticker is not found, a new row is inserted.
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

    dates = [r[0] for r in rows]
    lows = np.array([float(r[1]) for r in rows])

    result = core.best_under_trendline(lows)
    if result is None:
        print(f"No valid trendline found for {stock}.")
        return

    index1, index2, slope = result
    date1, date2 = dates[index1], dates[index2]
    date_diff = index2 - index1

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

    print(f"Updated under_trendlines for {stock}: Date1: {date1}, Date2: {date2}, Slope: {slope}, Date_diff: {date_diff}, Index2: {index2}")

@timed()
def check_and_update_under_trendline(stock, updated_dates):
    """
    Re-anchor the under trendline when any of the newly inserted dates is
    flagged update_trendline=TRUE and is newer than the current anchor (date2).
    Single query over all updated dates.
    """
    if not updated_dates:
        return

    cursor.execute("""
        SELECT MAX(date)
        FROM under_status
        WHERE ticker = %s AND update_trendline = TRUE AND date = ANY(%s::date[]);
    """, (stock, list(updated_dates)))
    last_update_trendline_date = cursor.fetchone()[0]

    if not last_update_trendline_date:
        return

    # Fetch the current date2 from under_trendlines
    cursor.execute("""
        SELECT date2
        FROM under_trendlines
        WHERE ticker = %s;
    """, (stock,))
    result = cursor.fetchone()

    if not result:
        raise ValueError(f"No trendline data found for {stock} in under_trendlines.")

    if last_update_trendline_date > result[0]:
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

# === Entry-quality filters (analyst layer) ===
VOLUME_CONFIRM_RATIO = 1.5   # breakout volume must exceed this multiple of the 20-day average
ATR_BUFFER_MULT = 0.5        # close must clear the trendline by this many ATRs to count as confirmed
ATR_SL_MULT = 1.5            # stop-loss distance in ATRs below entry
RR_TAKE_PROFIT = 2.0         # take-profit at this multiple of the SL risk (reward:risk)
REQUIRE_BULL_REGIME = True   # only open longs when SPY is above its 200-day MA
REGIME_TICKER = 'SPY'


@timed()
def fetch_entry_indicators():
    """
    ATR(14) and 20-day average volume for every ticker, as of the latest date.
    One window query over the recent slice of stock_prices.
    Returns DataFrame(ticker, atr14, avg_vol20).
    """
    query = """
        WITH recent AS (
            SELECT ticker, date, high, low, close, volume,
                   LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close
            FROM stock_prices
            WHERE date >= (SELECT MAX(date) FROM stock_prices) - INTERVAL '60 days'
        ),
        tr AS (
            SELECT ticker, date, volume,
                   GREATEST(high - low, ABS(high - prev_close), ABS(low - prev_close)) AS true_range,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM recent
            WHERE prev_close IS NOT NULL
        )
        SELECT ticker,
               AVG(true_range) FILTER (WHERE rn <= 14) AS atr14,
               AVG(volume) FILTER (WHERE rn <= 20) AS avg_vol20
        FROM tr
        GROUP BY ticker;
    """
    rows = fetch_query(query)
    return pd.DataFrame(rows, columns=["ticker", "atr14", "avg_vol20"])


@timed()
def is_bull_regime():
    """
    Market regime filter: True when SPY closes above its 200-day MA,
    False when below, None when SPY data is unavailable.
    """
    rows = fetch_query("""
        SELECT close FROM stock_prices
        WHERE ticker = %s
        ORDER BY date DESC
        LIMIT 200;
    """, (REGIME_TICKER,))
    if not rows or len(rows) < 200:
        return None
    closes = [float(r[0]) for r in rows]
    return closes[0] > (sum(closes) / len(closes))


@timed()
def update_upper_portfolio():
    upper_status_query = """
        SELECT date, ticker, breakthrough, update_trendline, trendline, duration_from_date2, distance, sequence
        FROM upper_status
        WHERE date = (SELECT MAX(date) FROM upper_status);
    """
    stock_prices_query = """
        SELECT date, ticker, close, low, volume FROM stock_prices
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
    stock_prices = pd.DataFrame(res_sp, columns=["date", "ticker", "close", "low", "volume"])

    # Market regime gate
    regime = is_bull_regime()
    if regime is None:
        print(f"⚠️ No {REGIME_TICKER} data for regime filter — proceeding without it.")
    elif REQUIRE_BULL_REGIME and not regime:
        print(f"🐻 {REGIME_TICKER} below its 200-day MA — no new upper entries today.")
        return

    indicators = fetch_entry_indicators()

    open_positions = pd.read_csv("open_positions.csv") if os.path.exists("open_positions.csv") else pd.DataFrame(
        columns=["date", "action", "strategy", "ticker", "price", "Profit/Loss %", "SL", "TP"]
    )
    positions = pd.read_csv("positions.csv") if os.path.exists("positions.csv") else pd.DataFrame(
        columns=["date", "action", "strategy", "ticker", "price", "Profit/Loss %", "SL", "TP"]
    )

    merged_data = upper_status.merge(stock_prices, on=["date", "ticker"], how="inner")
    merged_data = merged_data.merge(indicators, on="ticker", how="left")

    for _, row in merged_data.iterrows():
        ticker = row["ticker"]
        if not (
            row["breakthrough"]
            and not row["update_trendline"]
            and row["close"] > row["trendline"]
            and row["duration_from_date2"] > 50
            and row["sequence"] == 1
            and ticker not in open_positions["ticker"].values
        ):
            continue

        close = float(row["close"])
        trendline = float(row["trendline"])
        atr = float(row["atr14"]) if pd.notna(row["atr14"]) else None
        avg_vol = float(row["avg_vol20"]) if pd.notna(row["avg_vol20"]) else None
        volume = float(row["volume"]) if pd.notna(row["volume"]) else None

        # Volume confirmation: breakout must come on expanded volume
        if avg_vol and volume is not None and volume < VOLUME_CONFIRM_RATIO * avg_vol:
            continue

        # ATR buffer: close must clear the line by a real margin, not a rounding error
        if atr is not None and close <= trendline + ATR_BUFFER_MULT * atr:
            continue

        # ATR-based risk management (falls back to the old scheme when ATR is missing)
        if atr is not None:
            sl = round(close - ATR_SL_MULT * atr, 3)
            tp = round(close + RR_TAKE_PROFIT * (close - sl), 3)
        else:
            sl = min(row["low"], row["trendline"])
            tp = round(close * 1.1, 3)

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

    indicators = fetch_entry_indicators()
    merged_data = under_status.merge(stock_prices, on=["date", "ticker"], how="inner")
    merged_data = merged_data.merge(indicators, on="ticker", how="left")

    for _, row in merged_data.iterrows():
        ticker = row["ticker"]
        if (
            row["distance"] < 0
            and row["distance"] > -5
            and row["low"] <= row["trendline"]
            and row["duration_from_date2"] > 50
            and ticker not in open_positions["ticker"].values
        ):
            close = float(row["close"])
            atr = float(row["atr14"]) if pd.notna(row.get("atr14")) else None
            if atr is not None:
                sl = round(close - ATR_SL_MULT * atr, 3)
                tp = round(close + RR_TAKE_PROFIT * (close - sl), 3)
            else:
                sl = row["low"]
                tp = round(close * 1.1, 3)
            new_position = {
                "date": row["date"],
                "action": "buy",
                "strategy": "under",
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

    # Execute with parameter for stock only.
    # Use a savepoint so a failure (e.g. stock_dates table missing) only undoes
    # this statement, never earlier uncommitted work in the transaction.
    cursor.execute("SAVEPOINT sp_find_close;")
    try:
        cursor.execute(query, (stock,))
    except psycopg2.Error as e:
        cursor.execute("ROLLBACK TO SAVEPOINT sp_find_close;")
        print(f"⚠️ find_close_upper_trendline skipped for {stock}: {e}".splitlines()[0])
        return -1
    rows = cursor.fetchall()
    cursor.execute("RELEASE SAVEPOINT sp_find_close;")

    if not rows:
        print(f"No data found for {stock}.")
        return -1

    highs = np.array([float(r[1]) for r in rows])
    dates = [r[0] for r in rows]

    result = core.best_upper_trendline(highs)
    if result is None:
        return -1

    _, index2, _ = result
    date2 = dates[index2]

    cursor.execute(f"""
        UPDATE stock_dates
        SET d{d + 1} = %s
        WHERE ticker = %s;
    """, (date2, stock))
    connection.commit()

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

@timed()
def get_sequence_breakdown_by_date(date):
    """
    Get breakdown of tickers by sequence value (>0 vs =0) for a given date.

    Parameters:
        date: str or datetime - The date to analyze (format: 'YYYY-MM-DD')

    Returns:
        dict with keys:
            - 'date': the input date
            - 'sequence_gt_0_count': count of tickers with sequence > 0
            - 'sequence_eq_0_count': count of tickers with sequence = 0
            - 'sequence_gt_0_tickers': list of unique tickers with sequence > 0
            - 'sequence_eq_0_tickers': list of unique tickers with sequence = 0
    """
    # Convert to proper date format if needed
    if isinstance(date, str):
        date = pd.to_datetime(date).date()

    # Query for tickers with sequence > 0
    cursor.execute("""
        SELECT DISTINCT ticker
        FROM under_status_historical
        WHERE date = %s AND sequence > 0
        ORDER BY ticker;
    """, (date,))

    tickers_gt_0 = [row[0] for row in cursor.fetchall()]

    # Query for tickers with sequence = 0
    cursor.execute("""
        SELECT DISTINCT ticker
        FROM under_status_historical
        WHERE date = %s AND sequence = 0
        ORDER BY ticker;
    """, (date,))

    tickers_eq_0 = [row[0] for row in cursor.fetchall()]

    result = {
        'date': date,
        'sequence_gt_0_count': len(tickers_gt_0),
        'sequence_eq_0_count': len(tickers_eq_0),
        'sequence_gt_0_tickers': tickers_gt_0,
        'sequence_eq_0_tickers': tickers_eq_0
    }

    print(f"Date: {date}")
    print(f"Tickers with sequence > 0: {len(tickers_gt_0)}")
    print(f"Tickers with sequence = 0: {len(tickers_eq_0)}")

    return result

@timed()
def get_sequence_breakdown_for_filtered_tickers(check_date, start_date='2025-10-01', end_date=None):
    """
    Get sequence breakdown on a specific date for tickers that meet filtering criteria.

    The filtering criteria matches tickers that:
    - Have sequence = 0
    - breakthrough = false
    - duration_from_date2 > 150
    - current price < 70% of max price
    - low <= trendline AND close > trendline

    Parameters:
        check_date: str or datetime - The date to check sequence breakdown (e.g., '2025-10-31')
        start_date: str - Start date for filtering query (default: '2025-10-01')
        end_date: str or datetime - End date for filtering query (if None, uses check_date)

    Returns:
        dict with:
            - 'check_date': the date we're checking sequences for
            - 'filtered_tickers': list of tickers that meet the criteria
            - 'filtered_count': total number of filtered tickers
            - 'sequence_gt_0_count': count with sequence > 0 on check_date
            - 'sequence_eq_0_count': count with sequence = 0 on check_date
            - 'sequence_gt_0_tickers': list of tickers with sequence > 0
            - 'sequence_eq_0_tickers': list of tickers with sequence = 0
    """
    # Convert dates to proper format
    if isinstance(check_date, str):
        check_date = pd.to_datetime(check_date).date()

    if end_date is None:
        end_date = check_date
    elif isinstance(end_date, str):
        end_date = pd.to_datetime(end_date).date()

    # First, get the list of tickers that meet the filtering criteria
    cursor.execute("""
        SELECT DISTINCT ush.ticker
        FROM under_status_historical ush
        JOIN stock_prices sp ON ush.ticker = sp.ticker AND ush.date = sp.date
        JOIN ticker_extremes te ON ush.ticker = te.ticker
        WHERE ush.date > %s
          AND ush.date < %s
          AND ush.sequence = 0
          AND ush.breakthrough = false
          AND ush.duration_from_date2 > 150
          AND sp.close < (te.max_price * 0.7)
          AND sp.low <= ush.trendline
          AND sp.close > ush.trendline
        ORDER BY ush.ticker;
    """, (start_date, end_date))

    filtered_tickers = [row[0] for row in cursor.fetchall()]

    if not filtered_tickers:
        print(f"No tickers found matching the filter criteria between {start_date} and {end_date}")
        return {
            'check_date': check_date,
            'filtered_tickers': [],
            'filtered_count': 0,
            'sequence_gt_0_count': 0,
            'sequence_eq_0_count': 0,
            'sequence_gt_0_tickers': [],
            'sequence_eq_0_tickers': []
        }

    # Now check the sequence status for these tickers on the check_date
    tickers_tuple = tuple(filtered_tickers)

    # Query for sequence > 0 on check_date
    if len(filtered_tickers) == 1:
        cursor.execute("""
            SELECT DISTINCT ticker
            FROM under_status_historical
            WHERE date = %s
              AND ticker = %s
              AND sequence > 0
            ORDER BY ticker;
        """, (check_date, filtered_tickers[0]))
    else:
        cursor.execute("""
            SELECT DISTINCT ticker
            FROM under_status_historical
            WHERE date = %s
              AND ticker IN %s
              AND sequence > 0
            ORDER BY ticker;
        """, (check_date, tickers_tuple))

    tickers_gt_0 = [row[0] for row in cursor.fetchall()]

    # Query for sequence = 0 on check_date
    if len(filtered_tickers) == 1:
        cursor.execute("""
            SELECT DISTINCT ticker
            FROM under_status_historical
            WHERE date = %s
              AND ticker = %s
              AND sequence = 0
            ORDER BY ticker;
        """, (check_date, filtered_tickers[0]))
    else:
        cursor.execute("""
            SELECT DISTINCT ticker
            FROM under_status_historical
            WHERE date = %s
              AND ticker IN %s
              AND sequence = 0
            ORDER BY ticker;
        """, (check_date, tickers_tuple))

    tickers_eq_0 = [row[0] for row in cursor.fetchall()]

    result = {
        'check_date': check_date,
        'filtered_tickers': filtered_tickers,
        'filtered_count': len(filtered_tickers),
        'sequence_gt_0_count': len(tickers_gt_0),
        'sequence_eq_0_count': len(tickers_eq_0),
        'sequence_gt_0_tickers': tickers_gt_0,
        'sequence_eq_0_tickers': tickers_eq_0
    }

    print(f"\n{'='*60}")
    print(f"Filtered Query Results (between {start_date} and {end_date}):")
    print(f"Total filtered tickers: {len(filtered_tickers)}")
    print(f"\nSequence Breakdown on {check_date}:")
    print(f"  - Tickers with sequence > 0: {len(tickers_gt_0)}")
    print(f"  - Tickers with sequence = 0: {len(tickers_eq_0)}")
    print(f"{'='*60}\n")

    return result

@timed()
def get_sequence_breakdown_for_filtered_upper_tickers(check_date, start_date='2025-10-01', end_date=None):
    """
    Get price comparison breakdown on a specific date for tickers that meet upper breakthrough criteria.

    The filtering criteria matches tickers that:
    - Have sequence = 1
    - breakthrough = true
    - duration_from_date2 > 150
    - current price < 70% of max price

    Parameters:
        check_date: str or datetime - The date to check price comparisons (e.g., '2025-10-31')
        start_date: str - Start date for filtering query (default: '2025-10-01')
        end_date: str or datetime - End date for filtering query (if None, uses check_date)

    Returns:
        dict with:
            - 'check_date': the date we're checking prices for
            - 'filtered_tickers': list of tickers that meet the criteria
            - 'filtered_count': total number of filtered tickers
            - 'sequence_gt_1_count': count where check_date close > initial close
            - 'sequence_eq_1_count': count with sequence = 1 on check_date
            - 'sequence_eq_0_count': count where check_date close < initial close
            - 'sequence_gt_1_tickers': list of tickers with check_date close > initial close
            - 'sequence_eq_1_tickers': list of tickers with sequence = 1
            - 'sequence_eq_0_tickers': list of tickers with check_date close < initial close
    """
    # Convert dates to proper format
    if isinstance(check_date, str):
        check_date = pd.to_datetime(check_date).date()

    if end_date is None:
        end_date = check_date
    elif isinstance(end_date, str):
        end_date = pd.to_datetime(end_date).date()

    # First, get the list of tickers that meet the filtering criteria
    cursor.execute("""
        SELECT DISTINCT ush.ticker, ush.distance, sp.close
        FROM upper_status_historical ush
        JOIN stock_prices sp ON ush.ticker = sp.ticker AND ush.date = sp.date
        JOIN ticker_extremes te ON ush.ticker = te.ticker
        WHERE ush.date >= %s
          AND ush.date <= %s
          AND ush.sequence = 1
          AND ush.breakthrough = true
          AND ush.duration_from_date2 > 150
          AND sp.close < (te.max_price * 0.7)
        ORDER BY ush.ticker;
    """, (start_date, end_date))

    filtered_results = cursor.fetchall()
    filtered_tickers = [row[0] for row in filtered_results]
    ticker_distance_map = {row[0]: {'distance': row[1], 'close': row[2]} for row in filtered_results}

    if not filtered_tickers:
        print(f"No tickers found matching the upper breakthrough criteria between {start_date} and {end_date}")
        return {
            'check_date': check_date,
            'filtered_tickers': [],
            'filtered_count': 0,
            'sequence_gt_1_count': 0,
            'sequence_eq_1_count': 0,
            'sequence_eq_0_count': 0,
            'sequence_gt_1_tickers': [],
            'sequence_eq_1_tickers': [],
            'sequence_eq_0_tickers': []
        }

    # Now check price comparisons for these tickers on the check_date
    tickers_tuple = tuple(filtered_tickers)

    # Query for tickers where check_date close > current_price (from initial query)
    # This replaces the sequence > 1 check
    if len(filtered_tickers) == 1:
        cursor.execute("""
            SELECT DISTINCT ush.ticker, ush.distance, sp.close as check_date_close
            FROM upper_status_historical ush
            JOIN stock_prices sp ON ush.ticker = sp.ticker AND ush.date = sp.date
            WHERE ush.date = %s
              AND ush.ticker = %s
            ORDER BY ush.ticker;
        """, (check_date, filtered_tickers[0]))
    else:
        cursor.execute("""
            SELECT DISTINCT ush.ticker, ush.distance, sp.close as check_date_close
            FROM upper_status_historical ush
            JOIN stock_prices sp ON ush.ticker = sp.ticker AND ush.date = sp.date
            WHERE ush.date = %s
              AND ush.ticker IN %s
            ORDER BY ush.ticker;
        """, (check_date, tickers_tuple))

    check_date_results = cursor.fetchall()

    # Filter for close_price on check_date > current_price from query (replaces sequence > 1)
    tickers_gt_1 = []
    tickers_gt_1_with_distance = []
    for row in check_date_results:
        ticker, distance, check_date_close = row
        initial_close = ticker_distance_map[ticker]['close']
        if check_date_close > initial_close:
            tickers_gt_1.append(ticker)
            tickers_gt_1_with_distance.append({
                'ticker': ticker,
                'distance': distance,
                'close': check_date_close
            })

    # Filter for tickers that still have sequence = 1 (no change to this logic)
    if len(filtered_tickers) == 1:
        cursor.execute("""
            SELECT DISTINCT ticker, distance
            FROM upper_status_historical
            WHERE date = %s
              AND ticker = %s
              AND sequence = 1
            ORDER BY ticker;
        """, (check_date, filtered_tickers[0]))
    else:
        cursor.execute("""
            SELECT DISTINCT ticker, distance
            FROM upper_status_historical
            WHERE date = %s
              AND ticker IN %s
              AND sequence = 1
            ORDER BY ticker;
        """, (check_date, tickers_tuple))

    eq_1_results = cursor.fetchall()
    tickers_eq_1 = [row[0] for row in eq_1_results]
    tickers_eq_1_with_distance = [{'ticker': row[0], 'distance': row[1], 'close': ticker_distance_map[row[0]]['close']} for row in eq_1_results]

    # Filter for close_price on check_date < current_price from query (replaces sequence = 0)
    tickers_eq_0 = []
    tickers_eq_0_with_distance = []
    for row in check_date_results:
        ticker, distance, check_date_close = row
        initial_close = ticker_distance_map[ticker]['close']
        if check_date_close < initial_close:
            tickers_eq_0.append(ticker)
            tickers_eq_0_with_distance.append({
                'ticker': ticker,
                'distance': distance,
                'close': check_date_close
            })

    result = {
        'check_date': check_date,
        'filtered_tickers': filtered_tickers,
        'filtered_count': len(filtered_tickers),
        'sequence_gt_1_count': len(tickers_gt_1),
        'sequence_eq_1_count': len(tickers_eq_1),
        'sequence_eq_0_count': len(tickers_eq_0),
        'sequence_gt_1_tickers': tickers_gt_1,
        'sequence_eq_1_tickers': tickers_eq_1,
        'sequence_eq_0_tickers': tickers_eq_0,
        'sequence_gt_1_with_distance': tickers_gt_1_with_distance,
        'sequence_eq_1_with_distance': tickers_eq_1_with_distance,
        'sequence_eq_0_with_distance': tickers_eq_0_with_distance,
        'ticker_distance_map': ticker_distance_map
    }

    print(f"\n{'='*60}")
    print(f"Upper Breakthrough Query Results (between {start_date} and {end_date}):")
    print(f"Total filtered tickers: {len(filtered_tickers)}")
    print(f"\nPrice Comparison Breakdown on {check_date}:")
    print(f"  - Tickers with check_date close > initial close: {len(tickers_gt_1)} (price increased)")
    print(f"  - Tickers with sequence = 1: {len(tickers_eq_1)} (at breakthrough)")
    print(f"  - Tickers with check_date close < initial close: {len(tickers_eq_0)} (price decreased)")
    print(f"{'='*60}\n")

    return result

