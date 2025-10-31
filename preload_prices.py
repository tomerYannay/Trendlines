# preload_prices.py
import os
import time
import psycopg2
import requests
import pandas as pd
from typing import Optional, List, Set, Tuple
from psycopg2.extras import execute_values, DictCursor
from dotenv import load_dotenv

# -----------------------------
# Config & DB
# -----------------------------
load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USERNAME"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}
ALPHA_KEY = os.getenv("ALPHAVANTAGE_KEY", "8LLD101ZZ48BBVC8")  # שנה אם צריך
API_BASE = "https://www.alphavantage.co/query"

# בין קריאות API – כדי לעמוד ברייט-לימיט
SLEEP_BETWEEN_CALLS_SEC = 1.0


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


# -----------------------------
# Alpha Vantage helpers
# -----------------------------
def fetch_daily_adjusted(symbol: str, outputsize: str = "compact") -> dict:
    """
    מושך סדרת ימים מ-Alpha Vantage.
    מחזיר dict של 'Time Series (Daily)' או זורק שגיאה.
    outputsize: 'compact' (~100 ימים אחרונים) או 'full' (כל ההיסטוריה).
    """
    url = (
        f"{API_BASE}?function=TIME_SERIES_DAILY_ADJUSTED"
        f"&symbol={symbol}&outputsize={outputsize}&apikey={ALPHA_KEY}"
    )
    time.sleep(SLEEP_BETWEEN_CALLS_SEC)
    r = requests.get(url)
    if r.status_code != 200:
        raise ConnectionError(f"HTTP {r.status_code} for {symbol}")

    data = r.json()
    if "Time Series (Daily)" not in data:
        # הדפסה ידידותית לעזור בדיבאג
        raise ValueError(f"Bad response for {symbol}: {list(data.keys())[:4]}")
    return data["Time Series (Daily)"]


# -----------------------------
# DB helpers
# -----------------------------
def get_all_tickers(conn) -> List[str]:
    """
    מחזיר את כל הטיקרים מהטבלה tickers (עמודה בשם 'ticker').
    """
    with conn.cursor() as cur:
        cur.execute("SELECT ticker FROM tickers;")
        return [row[0] for row in cur.fetchall()]


def get_existing_dates_for_ticker(conn, symbol: str) -> Set[str]:
    """
    מחזיר סט של תאריכים שכבר קיימים בטבלת stock_prices לטיקר.
    (כדי להימנע מהכנסות כפולות)
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT date::text FROM stock_prices WHERE ticker = %s;",
            (symbol,),
        )
        return {r[0] for r in cur.fetchall()}


def get_latest_db_date(conn, symbol: str) -> Optional[str]:
    """
    מחזיר את התאריך המקסימלי שקיים ב-DB לטיקר או None אם אין כלל.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(date) FROM stock_prices WHERE ticker = %s;",
            (symbol,),
        )
        row = cur.fetchone()
        return row[0].strftime("%Y-%m-%d") if row and row[0] else None


def rows_from_series(symbol: str, series: dict, skip_dates: Set[str]) -> List[Tuple]:
    """
    ממיר את ה־dict של Alpha Vantage לרשימת שורות להכנסה ל-DB.
    מדלג על תאריכים שכבר קיימים.
    """
    rows = []
    # סדר כרונולוגי עולה (לא חובה, אבל נחמד)
    for dt in sorted(series.keys()):
        if dt in skip_dates:
            continue
        day = series[dt]
        try:
            o = float(day["1. open"])
            h = float(day["2. high"])
            l = float(day["3. low"])
            c = float(day["4. close"])
            v = day.get("6. volume")
            v = int(v) if v not in (None, "", "None") else 0
        except Exception as e:
            # אם יש בעיה בפרסינג – נדלג רק על היום הזה ונמשיך
            print(f"⚠️ {symbol} {dt} parse error: {e} (skipping)")
            continue

        rows.append((symbol, dt, o, h, l, c, v))
    return rows


def upsert_prices(conn, rows: List[Tuple]):
    """
    מכניס באצווה לטבלת stock_prices.
    סכימה: (ticker, date, open, high, low, close, volume)
    """
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO stock_prices (ticker, date, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (ticker, date) DO NOTHING;
            """,
            rows,
        )
    conn.commit()
    return len(rows)


# -----------------------------
# Orchestration
# -----------------------------
def backfill_one_ticker(conn, symbol: str):
    """
    משלים ימים חסרים לטיקר בודד:
    - אם אין בכלל נתונים לטיקר -> מושך FULL
    - אחרת -> COMPact (מספיק לכסות חורים סבירים + היום האחרון)
    """
    latest_db_date = get_latest_db_date(conn, symbol)
    mode = "full" if latest_db_date is None else "compact"

    try:
        series = fetch_daily_adjusted(symbol, mode)
    except Exception as e:
        print(f"❌ {symbol}: fetch failed ({mode}): {e}")
        return

    existing_dates = get_existing_dates_for_ticker(conn, symbol)
    to_insert = rows_from_series(symbol, series, existing_dates)
    inserted = upsert_prices(conn, to_insert)

    if inserted:
        print(f"✅ {symbol}: inserted {inserted} day(s) via {mode}")
    else:
        print(f"ℹ️ {symbol}: up to date (mode={mode})")


def backfill_all_prices():
    """
    עובר על כל הטיקרים ומבצע השלמה לפני שאר התהליכים.
    """
    with get_connection() as conn:
        tickers = get_all_tickers(conn)
        print(f"Found {len(tickers)} tickers.")
        for i, symbol in enumerate(tickers, 1):
            print(f"[{i}/{len(tickers)}] Backfilling {symbol} ...")
            backfill_one_ticker(conn, symbol)
            # אם אתה על חשבון חינמי, אולי תרצה לישון יותר בין טיקרים
            # time.sleep(12)


if __name__ == "__main__":
    backfill_all_prices()
    print("🎉 Backfill done. You can now run the rest of your pipeline.")
