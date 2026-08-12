# #!/usr/bin/env python3
# """
# Fetch all historical 1D OHLC bars for TSLA from Interactive Brokers (IBKR)
# using ib_insync. Saves a CSV if requested.

# Usage:
#     python fetch_tsla_1d_from_ib.py
# """

from datetime import datetime, timezone
from time import sleep

import pandas as pd
from ib_insync import IB, Stock, util

# ---- Config ----
HOST = "127.0.0.1"     # TWS/Gateway host
PORT = 4001            # 7497 = TWS paper, 7496 = TWS live; Gateway defaults differ
CLIENT_ID = 19         # any positive int; change if you run multiple clients

TICKER = "TSLA"
SAVE_CSV_PATH = "research/output/TSLA_1D_IB.csv"  # set to None to skip saving
MARKET_DATA_TYPE = 3    # 1=real-time, 2=frozen, 3=delayed, 4=delayed-frozen

# IB pacing: keep a small delay between successive historical pulls
PACING_SLEEP_SECS = 0.23

# ---- Helper: request a chunk of daily bars ----
def fetch_hist_chunk(ib: IB, contract: Stock, end_dt: datetime | str, duration: str) -> list:
    """
    Request a chunk of 1-day bars.
    - end_dt: datetime (UTC) or '' for 'now' per IB API; or IB date string "YYYYMMDD HH:MM:SS"
    - duration examples: '1 Y', '5 Y', '30 Y'
    """
    bars = ib.reqHistoricalData(
        contract=contract,
        endDateTime=end_dt,
        durationStr=duration,
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=False,          # set True to get only RTH bars
        formatDate=1,          # 1 = human-readable date
        keepUpToDate=False
    )
    return bars

def bars_to_df(bars) -> pd.DataFrame:
    df = util.df(bars)
    if not df.empty:
        # Normalize columns we care about
        df = df.rename(columns={
            'date': 'date',
            'open': 'open',
            'high': 'high',
            'low':  'low',
            'close':'close',
            'volume':'volume'
        })
        # Ensure datetime is timezone-aware (UTC)
        df['date'] = pd.to_datetime(df['date'], utc=True)
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']].sort_values('date')
        df = df.drop_duplicates(subset='date', keep='last').reset_index(drop=True)
    return df

def backfill_all_daily(ib: IB, symbol: str) -> pd.DataFrame:
    """
    Fetch as much 1D history as IB will provide in the fewest calls possible.
    Many setups allow '30 Y' in a single call; if not, we paginate backwards.
    """
    # Define TSLA contract
    contract = Stock(symbol, 'SMART', 'USD', primaryExchange='NASDAQ')

    # Qualify contract to populate conId/exchanges properly
    ib.qualifyContracts(contract)

    # Try a single wide grab first (many IBKR accounts allow '30 Y' with 1d bars)
    try:
        big = fetch_hist_chunk(ib, contract, end_dt='', duration='30 Y')
        df = bars_to_df(big)
        if not df.empty:
            return df
    except Exception:
        # Fall back to pagination below
        pass

    # Fallback pagination: pull in chunks (1 Y each) backwards until no older data appears
    all_df = pd.DataFrame(columns=['date','open','high','low','close','volume'])
    end_dt = ''  # '' = now
    last_oldest = None

    while True:
        bars = fetch_hist_chunk(ib, contract, end_dt=end_dt, duration='1 Y')
        chunk = bars_to_df(bars)
        if chunk.empty:
            break

        # Merge
        before_merge_len = len(all_df)
        all_df = pd.concat([all_df, chunk], ignore_index=True)
        all_df = all_df.drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)

        # Stop if we didn't extend older boundary
        new_oldest = all_df['date'].min() if not all_df.empty else None
        if last_oldest is not None and new_oldest == last_oldest:
            break
        last_oldest = new_oldest

        # Prepare next end time = earliest date we have, minus a minute
        earliest = chunk['date'].min()
        # Convert to IB expected string format in US/Eastern or UTC works; IB accepts "YYYYMMDD HH:MM:SS"
        end_dt = earliest.strftime('%Y%m%d %H:%M:%S')

        sleep(PACING_SLEEP_SECS)

    return all_df

def main():
    ib = IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID, readonly=True)
    ib.reqMarketDataType(MARKET_DATA_TYPE)

    try:
        df = backfill_all_daily(ib, TICKER)
    finally:
        ib.disconnect()

    if df.empty:
        print("No data returned.")
        return

    if SAVE_CSV_PATH:
        df.to_csv(SAVE_CSV_PATH, index=False)
        print(f"Saved {len(df)} rows to {SAVE_CSV_PATH}")

    # Show head/tail preview
    print(df.head(3).to_string(index=False))
    print(" ... ")
    print(df.tail(3).to_string(index=False))
    print(f"Total rows: {len(df)}  |  Range: {df['date'].min()} → {df['date'].max()}")

if __name__ == "__main__":
    main()

# from ib_insync import IB
# ib = IB()
# ib.connect('127.0.0.1', 4001, clientId=19, readonly=True)  # שנה פורט לפי שלב 2
# print('Connected:', ib.isConnected())
# ib.disconnect()
