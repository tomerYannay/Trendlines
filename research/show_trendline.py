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
               us.duration_from_date2, us.sequence, us.breakthrough,
               uns.trendline AS under_trendline, uns.distance AS under_distance
        FROM upper_status us
        JOIN upper_trendlines ut ON ut.ticker = us.ticker
        JOIN stock_prices sp ON sp.ticker = us.ticker AND sp.date = us.date
        LEFT JOIN under_status uns ON uns.ticker = us.ticker AND uns.date = us.date
        WHERE us.date = (SELECT MAX(date) FROM upper_status)
          AND us.duration_from_date2 >= %s
        ORDER BY us.breakthrough DESC, ABS(us.distance) ASC
        LIMIT %s;
    """, (min_days, limit))
    df = pd.DataFrame(rows, columns=[
        'ticker', 'date1', 'date2', 'slope', 'date', 'upper_line',
        'close', 'to_upper_%', 'days_since_d2', 'sequence', 'breakthrough',
        'under_line', 'under_distance'
    ])
    df['slope_yr_%'] = ((np.exp(df['slope'].astype(float) * 252) - 1) * 100).round(1)
    df['to_upper_%'] = df['to_upper_%'].astype(float).round(2)
    # under_status.distance = (line-close)/close*100 (negative when price above support);
    # show it as % ABOVE support (positive = healthy cushion)
    df['above_support_%'] = (-df['under_distance'].astype(float)).round(2)
    cols = ['ticker', 'date1', 'date2', 'slope_yr_%', 'upper_line', 'close', 'under_line',
            'to_upper_%', 'above_support_%', 'days_since_d2', 'sequence', 'breakthrough']
    print(f"\nDiagonals as of {df['date'].iloc[0]} — sorted by closeness to upper breakout")
    print("(to_upper_% = distance below the resistance line; above_support_% = cushion above the support line)\n")
    print(df[cols].to_string(index=False))


def show_all_under(limit, min_days=50, min_price=2.0):
    """All tickers sorted by closeness to their SUPPORT (under) diagonal."""
    rows = db.fetch_query("""
        SELECT us.ticker, ut.date1, ut.date2, ut.slope,
               us.date, us.trendline, sp.close, sp.low, us.distance,
               us.duration_from_date2, us.sequence, us.breakthrough,
               ups.distance AS upper_distance
        FROM under_status us
        JOIN under_trendlines ut ON ut.ticker = us.ticker
        JOIN stock_prices sp ON sp.ticker = us.ticker AND sp.date = us.date
        LEFT JOIN upper_status ups ON ups.ticker = us.ticker AND ups.date = us.date
        WHERE us.date = (SELECT MAX(date) FROM under_status)
          AND us.duration_from_date2 >= %s
          AND sp.close >= %s
        ORDER BY us.breakthrough DESC, ABS(us.distance) ASC
        LIMIT %s;
    """, (min_days, min_price, limit))
    df = pd.DataFrame(rows, columns=[
        'ticker', 'date1', 'date2', 'slope', 'date', 'support_line',
        'close', 'low', 'distance', 'days_since_d2', 'sequence', 'breakthrough',
        'upper_distance'
    ])
    df['slope_yr_%'] = ((np.exp(df['slope'].astype(float) * 252) - 1) * 100).round(1)
    # under_status.distance = (line-close)/close*100 → negative when price above support
    df['above_support_%'] = (-df['distance'].astype(float)).round(2)
    df['to_upper_%'] = df['upper_distance'].astype(float).round(2)
    df['low_touched'] = df['low'].astype(float) <= df['support_line'].astype(float)
    cols = ['ticker', 'date1', 'date2', 'slope_yr_%', 'support_line', 'close',
            'above_support_%', 'low_touched', 'to_upper_%', 'days_since_d2', 'sequence', 'breakthrough']
    print(f"\nSupport diagonals as of {df['date'].iloc[0]} — sorted by closeness to the support line")
    print("(above_support_% = close above the line; breakthrough=True = closed BELOW support;")
    print(" low_touched = today's low reached the line — the bounce-strategy trigger)\n")
    print(df[cols].to_string(index=False))


def _print_line_detail(ticker, side):
    """side: 'upper' (resistance, anchored on highs) or 'under' (support, anchored on lows)."""
    tl_table = f"{side}_trendlines"
    st_table = f"{side}_status"
    price_col = 'high' if side == 'upper' else 'low'
    anchor1_name = 'all-time high' if side == 'upper' else 'all-time low'

    row = db.fetch_query(f"""
        SELECT ut.date1, ut.date2, ut.slope, ut.date_diff,
               us.date, us.trendline, sp.close, us.distance,
               us.duration_from_date2, us.sequence, us.breakthrough
        FROM {tl_table} ut
        JOIN {st_table} us ON us.ticker = ut.ticker
            AND us.date = (SELECT MAX(date) FROM {st_table} WHERE ticker = ut.ticker)
        JOIN stock_prices sp ON sp.ticker = ut.ticker AND sp.date = us.date
        WHERE ut.ticker = %s;
    """, (ticker,))
    if not row:
        print(f"\n=== {ticker} — {side} diagonal ===\n(none — possibly at {anchor1_name}, delisted, or not in DB)")
        return

    d1, d2, slope, ddiff, date, tl, close, dist, dur2, seq, bt = row[0]
    p1 = db.fetch_query(f"SELECT {price_col} FROM stock_prices WHERE ticker=%s AND date=%s;", (ticker, d1))[0][0]
    p2 = db.fetch_query(f"SELECT {price_col} FROM stock_prices WHERE ticker=%s AND date=%s;", (ticker, d2))[0][0]
    slope = float(slope)
    dist = float(dist)

    label = 'resistance (highs)' if side == 'upper' else 'support (lows)'
    position = (f"{dist:.2f}% below the line" if side == 'upper'
                else f"{-dist:.2f}% above the line")
    print(f"\n=== {ticker} — {side} diagonal [{label}] ===")
    print(f"Anchor 1 ({anchor1_name}): {d1}  @ {float(p1):.2f}")
    print(f"Anchor 2 (extreme slope): {d2}  @ {float(p2):.2f}   ({ddiff} trading days apart)")
    print(f"Slope: {slope:.6f} per trading day (log)  =  {(np.exp(slope * 252) - 1) * 100:+.1f}%/year")
    print(f"As of {date}:  line={float(tl):.2f}  close={float(close):.2f}  ({position})")
    print(f"Days since d2: {dur2}   Sequence: {seq}   Breakthrough: {bt}")


def show_one(ticker):
    _print_line_detail(ticker, 'upper')
    _print_line_detail(ticker, 'under')


def plot_one(ticker):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    import trendline_core as core
    import os

    upper = db.fetch_query("SELECT date1, date2, slope FROM upper_trendlines WHERE ticker=%s;", (ticker,))
    under = db.fetch_query("SELECT date1, date2, slope FROM under_trendlines WHERE ticker=%s;", (ticker,))
    if not upper and not under:
        print(f"{ticker}: no trendlines to plot")
        return

    rows = db.fetch_query("""
        SELECT date, high, low, close FROM stock_prices WHERE ticker=%s ORDER BY date;
    """, (ticker,))
    df = pd.DataFrame(rows, columns=['date', 'high', 'low', 'close'])
    for c in ('high', 'low', 'close'):
        df[c] = df[c].astype(float)

    idx = {d: i for i, d in enumerate(df['date'])}
    n = len(df)

    fig, ax = plt.subplots(figsize=(14, 7))
    start = n  # earliest anchor decides how far back the chart goes

    if upper:
        d1, d2, slope = upper[0]
        i1, i2 = idx[d1], idx[d2]
        line = core.trendline_prices(n, i2, df['high'].iloc[i2], float(slope))
        ax.plot(df['date'], line, color='#d62728', lw=1.8, label='Upper diagonal (resistance)')
        ax.scatter([d1, d2], [df['high'].iloc[i1], df['high'].iloc[i2]],
                   color='#d62728', zorder=5, s=45)
        start = min(start, i1)

    if under:
        d1u, d2u, slope_u = under[0]
        j1, j2 = idx[d1u], idx[d2u]
        line_u = core.trendline_prices(n, j2, df['low'].iloc[j2], float(slope_u))
        ax.plot(df['date'], line_u, color='#2ca02c', lw=1.8, label='Under diagonal (support)')
        ax.scatter([d1u, d2u], [df['low'].iloc[j1], df['low'].iloc[j2]],
                   color='#2ca02c', zorder=5, s=45)
        start = min(start, j1)

    ax.plot(df['date'], df['close'], color='#222', lw=1.0, label='Close')

    start = max(0, start - 60)
    ax.set_xlim(df['date'].iloc[start], df['date'].iloc[-1])
    visible = df.iloc[start:]
    ax.set_ylim(visible['low'].min() * 0.9, visible['high'].max() * 1.1)
    ax.set_yscale('log')
    ax.set_title(f"{ticker} — resistance & support diagonals (log scale)")
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
    ap.add_argument('--side', choices=['upper', 'under'], default='upper',
                    help="table view: 'upper' = closest to resistance breakout (default); 'under' = closest to the support line")
    ap.add_argument('--min-price', type=float, default=2.0,
                    help='under table: minimum close price to filter penny-stock noise (default 2.0)')
    ap.add_argument('--plot', action='store_true', help='save a chart with the diagonal')
    args = ap.parse_args()

    if args.ticker:
        t = args.ticker.upper()
        show_one(t)
        if args.plot:
            plot_one(t)
    elif args.side == 'under':
        show_all_under(args.n, args.min_days, args.min_price)
    else:
        show_all(args.n, args.min_days)


if __name__ == '__main__':
    main()
