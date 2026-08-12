"""
Inspect the upper trendline (diagonal) of any ticker.

Usage (from the project root):

    python -m research.show_trendline                # all tickers, sorted by distance to breakout
    python -m research.show_trendline -n 30          # top 30 closest to breakout
    python -m research.show_trendline AAON           # full detail for one ticker
    python -m research.show_trendline AAON --plot    # + save a chart to alpha/plot/AAON_diagonal.png
"""
import argparse
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db


def show_all(limit, min_days=50):
    rows = db.fetch_query("""
        SELECT us.ticker, ut.date1, ut.date2, ut.slope,
               us.date, us.trendline, sp.close, us.distance,
               us.duration_from_date2, us.sequence, us.breakthrough
        FROM upper_status us
        JOIN upper_trendlines ut ON ut.ticker = us.ticker
        JOIN stock_prices sp ON sp.ticker = us.ticker AND sp.date = us.date
        WHERE us.date = (SELECT MAX(date) FROM upper_status)
          AND us.duration_from_date2 >= %s
        ORDER BY us.breakthrough DESC, ABS(us.distance) ASC
        LIMIT %s;
    """, (min_days, limit))
    df = pd.DataFrame(rows, columns=[
        'ticker', 'date1', 'date2', 'slope', 'date', 'trendline',
        'close', 'distance_%', 'days_since_d2', 'sequence', 'breakthrough'
    ])
    df['slope_yr_%'] = (np.exp(df['slope'].astype(float) * 252) - 1) * 100  # annualized
    df['distance_%'] = df['distance_%'].astype(float).round(2)
    df['slope_yr_%'] = df['slope_yr_%'].round(1)
    cols = ['ticker', 'date1', 'date2', 'slope_yr_%', 'trendline', 'close',
            'distance_%', 'days_since_d2', 'sequence', 'breakthrough']
    print(f"\nUpper diagonals as of {df['date'].iloc[0]} — sorted by closeness to breakout")
    print("(distance_% = how far the close is BELOW the line; negative = above it)\n")
    print(df[cols].to_string(index=False))


def show_one(ticker):
    row = db.fetch_query("""
        SELECT ut.date1, ut.date2, ut.slope, ut.date_diff,
               us.date, us.trendline, sp.close, sp.high, us.distance,
               us.duration_from_date2, us.sequence, us.breakthrough
        FROM upper_trendlines ut
        JOIN upper_status us ON us.ticker = ut.ticker
            AND us.date = (SELECT MAX(date) FROM upper_status WHERE ticker = ut.ticker)
        JOIN stock_prices sp ON sp.ticker = ut.ticker AND sp.date = us.date
        WHERE ut.ticker = %s;
    """, (ticker,))
    if not row:
        print(f"{ticker}: no upper trendline (possibly at all-time high, delisted, or not in DB)")
        return

    d1, d2, slope, ddiff, date, tl, close, high, dist, dur2, seq, bt = row[0]
    p1 = db.fetch_query("SELECT high FROM stock_prices WHERE ticker=%s AND date=%s;", (ticker, d1))[0][0]
    p2 = db.fetch_query("SELECT high FROM stock_prices WHERE ticker=%s AND date=%s;", (ticker, d2))[0][0]
    slope = float(slope)

    print(f"\n=== {ticker} — upper diagonal ===")
    print(f"Anchor 1 (all-time high): {d1}  @ {float(p1):.2f}")
    print(f"Anchor 2 (max slope)    : {d2}  @ {float(p2):.2f}   ({ddiff} trading days apart)")
    print(f"Slope: {slope:.6f} per trading day (log)  =  {(np.exp(slope * 252) - 1) * 100:+.1f}%/year")
    print(f"\nAs of {date}:")
    print(f"  Trendline price : {float(tl):.2f}")
    print(f"  Close           : {float(close):.2f}")
    print(f"  Distance        : {float(dist):.2f}% below the line")
    print(f"  Days since d2   : {dur2}   Sequence: {seq}   Breakthrough: {bt}")


def plot_one(ticker):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    import trendline_core as core
    import os

    tl = db.fetch_query("SELECT date1, date2, slope FROM upper_trendlines WHERE ticker=%s;", (ticker,))
    if not tl:
        print(f"{ticker}: no trendline to plot")
        return
    d1, d2, slope = tl[0]

    rows = db.fetch_query("""
        SELECT date, high, close FROM stock_prices WHERE ticker=%s ORDER BY date;
    """, (ticker,))
    df = pd.DataFrame(rows, columns=['date', 'high', 'close'])
    df['high'] = df['high'].astype(float)
    df['close'] = df['close'].astype(float)

    idx = {d: i for i, d in enumerate(df['date'])}
    i1, i2 = idx[d1], idx[d2]
    line = core.trendline_prices(len(df), i2, df['high'].iloc[i2], float(slope))

    # show from a bit before anchor 1
    start = max(0, i1 - 60)
    sl = slice(start, len(df))

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(df['date'][sl], df['close'][sl], color='#222', lw=1.0, label='Close')
    ax.plot(df['date'][sl], line[sl], color='#d62728', lw=1.8, label='Upper diagonal')
    ax.scatter([d1, d2], [df['high'].iloc[i1], df['high'].iloc[i2]],
               color='#d62728', zorder=5, s=45, label='Anchors (highs)')
    ax.set_yscale('log')
    ax.set_title(f"{ticker} — upper diagonal  {d1} → {d2}  (log scale)")
    ax.legend()
    ax.grid(alpha=0.3)
    os.makedirs('alpha/plot', exist_ok=True)
    out = f"alpha/plot/{ticker}_diagonal.png"
    fig.savefig(out, dpi=130, bbox_inches='tight')
    print(f"chart saved: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ticker', nargs='?', help='ticker symbol (omit for a full table)')
    ap.add_argument('-n', type=int, default=40, help='rows in the table view (default 40)')
    ap.add_argument('--min-days', type=int, default=50,
                    help='table view: minimum trading days since anchor 2 (default 50, matching the strategy filter)')
    ap.add_argument('--plot', action='store_true', help='save a chart with the diagonal')
    args = ap.parse_args()

    if args.ticker:
        t = args.ticker.upper()
        show_one(t)
        if args.plot:
            plot_one(t)
    else:
        show_all(args.n, args.min_days)


if __name__ == '__main__':
    main()
