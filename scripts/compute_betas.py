import psycopg2
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

db_config = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
}

def fetch_prices():
    with psycopg2.connect(**db_config) as conn:
        query = """
        SELECT date, ticker, close
        FROM stock_prices
        WHERE date >= CURRENT_DATE - INTERVAL '400 days'
        """
        return pd.read_sql(query, conn)

def calculate_beta(stock_returns, market_returns):
    if len(stock_returns) != len(market_returns):
        return None
    return stock_returns.cov(market_returns) / market_returns.var()

def compute_and_store_betas():
    df = fetch_prices()
    df['date'] = pd.to_datetime(df['date'])
    tickers = df['ticker'].unique()
    market = df[df['ticker'] == 'SPY'].copy()
    market = market.set_index('date').sort_index()
    market_returns = market['close'].pct_change().dropna()

    today = market.index.max()
    one_year_ago = today - timedelta(days=365)
    one_month_ago = today - timedelta(days=30)

    records = []

    for ticker in tickers:
        if ticker == 'SPY':
            continue

        stock_df = df[df['ticker'] == ticker].set_index('date').sort_index()
        stock_returns = stock_df['close'].pct_change().dropna()

        aligned = pd.DataFrame({'stock': stock_returns}).join(
            pd.DataFrame({'market': market_returns}), how='inner'
        ).dropna()

        print(f"Ticker: {ticker}, aligned rows: {len(aligned)}")

        if len(aligned) < 30:
            print(f"Skipping {ticker} — not enough data.")
            continue

        # Calculate Beta
        beta_1y = calculate_beta(
            aligned[aligned.index >= one_year_ago]['stock'],
            aligned[aligned.index >= one_year_ago]['market']
        )
        beta_1m = calculate_beta(
            aligned[aligned.index >= one_month_ago]['stock'],
            aligned[aligned.index >= one_month_ago]['market']
        )

        # Calculate Average Daily Move
        abs_returns = aligned['stock'].abs()
        avg_move_1y = abs_returns[aligned.index >= one_year_ago].mean() * 100
        avg_move_1m = abs_returns[aligned.index >= one_month_ago].mean() * 100

        print(f"{ticker} | Beta 1Y: {beta_1y:.4f}, Beta 1M: {beta_1m:.4f}, Avg Move 1Y: {avg_move_1y:.2f}%, Avg Move 1M: {avg_move_1m:.2f}%")

        records.append((ticker, today.date(), beta_1y, beta_1m, avg_move_1y, avg_move_1m))

    # Insert into DB
    with psycopg2.connect(**db_config) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_betas (
                    ticker TEXT,
                    date DATE,
                    beta_1y NUMERIC,
                    beta_1m NUMERIC,
                    average_daily_move_1y NUMERIC,
                    average_daily_move_1m NUMERIC,
                    PRIMARY KEY (ticker, date)
                )
            """)
            cursor.executemany("""
                INSERT INTO stock_betas (
                    ticker, date, beta_1y, beta_1m, average_daily_move_1y, average_daily_move_1m
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, date) DO UPDATE
                SET beta_1y = EXCLUDED.beta_1y,
                    beta_1m = EXCLUDED.beta_1m,
                    average_daily_move_1y = EXCLUDED.average_daily_move_1y,
                    average_daily_move_1m = EXCLUDED.average_daily_move_1m;
            """, records)
        conn.commit()

