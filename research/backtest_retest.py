"""
Breakout vs. Retest-entry backtest (upper diagonal, long-only).

Walk-forward replay of the live pipeline (same re-anchoring rules as
backtest_frozen_diagonals, dynamic mode). For every upper-diagonal BREAKOUT
signal, two entries are compared:

  * BREAKOUT entry : buy at the close of the breakout candle (the baseline)
  * RETEST entry   : wait up to --window trading days for a pullback that
                     touches the broken line (low <= line * (1 + tol%)) while
                     the close still holds above the line -> buy at that close.
                     - close falls back below the line  -> FAILED breakout, no trade
                     - no touch within the window       -> NO_RETEST (runaway), no trade

The retest is always measured against the line that was actually broken
(frozen at the breakout candle), even if the live rules re-anchor a new
diagonal in the meantime.

Usage (from the project root):
    python -m research.backtest_retest --as-of 2025-07-01
    python -m research.backtest_retest --as-of 2025-07-01 --min-days 50
    python -m research.backtest_retest --window 10 --tol 2
"""
import argparse
import os
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import trendline_core as core
from research.backtest_frozen_diagonals import load_prices, forward_returns, spy_benchmark, HORIZONS

COOLDOWN = 20


def analyze_ticker(ticker, as_of, min_price, seq_days, extreme_pct, window, tol_pct, min_days):
    df = load_prices(ticker)
    if df is None or len(df) < 60:
        return []

    dates = df['date'].tolist()
    n = len(df)
    hist_n = sum(1 for d in dates if pd.Timestamp(d) < as_of)
    if hist_n < 60 or hist_n == n:
        return []

    highs, lows, closes = df['high'].values, df['low'].values, df['close'].values

    up = core.best_upper_trendline(highs[:hist_n])
    if up is None:
        return []
    up_state = (up[1], highs[up[1]], up[2])
    up_seq, up_prev_bt, last_event = 0, False, -10**9

    signals = []
    pending = None   # open retest watch: {'t0', 'i2', 'p2', 'slope', 'signal'}

    def broken_line_at(p, t):
        return float(np.exp(np.log(p['p2']) + p['slope'] * (t - p['i2'])))

    for t in range(hist_n, n):
        # ---- progress an open retest watch (against the ORIGINAL broken line) ----
        if pending is not None:
            lp = broken_line_at(pending, t)
            sig = pending['signal']
            if closes[t] < lp:
                sig['outcome'] = 'failed'                      # closed back below -> no trade
                pending = None
            elif lows[t] <= lp * (1 + tol_pct / 100) and closes[t] > lp:
                sig['outcome'] = 'entered'
                sig['days_to_retest'] = t - pending['t0']
                sig['retest_close'] = round(closes[t], 2)
                for k, v in forward_returns(closes, t).items():
                    sig[f'retest_{k}'] = v
                pending = None
            elif t - pending['t0'] >= window:
                sig['outcome'] = 'no_retest'                   # ran away without a pullback
                pending = None

        # ---- line in force (live rules) ----
        i2, p2, slope = up_state
        line_t = float(np.exp(np.log(p2) + slope * (t - i2)))
        bt = closes[t] > line_t
        dist = (line_t - closes[t]) / closes[t] * 100
        seq = up_seq + 1 if bt else 0

        # ---- new breakout signal ----
        if (bt and up_seq == 0 and pending is None
                and t - last_event > COOLDOWN
                and closes[t] >= min_price
                and (t - i2) >= min_days):
            sig = {
                'ticker': ticker, 'event_date': dates[t],
                'breakout_close': round(closes[t], 2),
                'line_price': round(line_t, 2),
                'slope_yr_%': round((np.exp(slope * 252) - 1) * 100, 1),
                'days_since_anchor': t - i2,
                'outcome': 'no_retest',      # overwritten by the watch loop
            }
            for k, v in forward_returns(closes, t).items():
                sig[f'breakout_{k}'] = v
            signals.append(sig)
            pending = {'t0': t, 'i2': i2, 'p2': p2, 'slope': slope, 'signal': sig}
            last_event = t

        # ---- live re-anchor rules ----
        update_flag = (seq > seq_days) or (dist > 0 and up_prev_bt) or (dist < -extreme_pct)
        up_seq, up_prev_bt = seq, bt
        if update_flag:
            res = core.best_upper_trendline(highs[:t + 1])
            if res is not None:
                up_state = (res[1], highs[res[1]], res[2])
                up_seq, up_prev_bt = 0, False

    return signals


def stats_line(s):
    s = s.dropna().astype(float)
    if s.empty:
        return "n=0"
    return f"n={len(s):4d}  win={100 * (s > 0).mean():5.1f}%  avg={s.mean():+6.2f}%  med={s.median():+6.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-of', default='2025-07-01')
    ap.add_argument('--min-price', type=float, default=2.0)
    ap.add_argument('--min-days', type=int, default=0, help='line maturity (trading days past anchor) required at breakout')
    ap.add_argument('--seq-days', type=int, default=200, help='re-anchor after N consecutive closes above (default 200)')
    ap.add_argument('--extreme-pct', type=float, default=100.0, help='re-anchor when close is this %% beyond the line (default 100)')
    ap.add_argument('--window', type=int, default=15, help='trading days to wait for the retest (default 15)')
    ap.add_argument('--tol', type=float, default=1.0, help='touch tolerance: low within this %% above the line (default 1.0)')
    args = ap.parse_args()

    as_of = pd.Timestamp(args.as_of)
    db.cursor.execute("SELECT ticker FROM tickers_russell ORDER BY ticker;")
    tickers = [r[0] for r in db.cursor.fetchall()]
    print(f"Breakout vs retest | as-of {as_of.date()} | window={args.window}d tol={args.tol}% "
          f"| renewal: seq>{args.seq_days} / {args.extreme_pct}% | min-days={args.min_days}")

    signals = []
    for i, t in enumerate(tickers, 1):
        try:
            signals.extend(analyze_ticker(t, as_of, args.min_price, args.seq_days,
                                          args.extreme_pct, args.window, args.tol, args.min_days))
        except Exception as e:
            print(f"  error {t}: {e}")
        if i % 400 == 0:
            print(f"  ...{i}/{len(tickers)}")

    ev = pd.DataFrame(signals)
    if ev.empty:
        print("No signals.")
        return

    n = len(ev)
    print(f"\ntotal breakout signals: {n}")
    for oc in ('entered', 'failed', 'no_retest'):
        cnt = (ev['outcome'] == oc).sum()
        print(f"  {oc:10s}: {cnt:5d}  ({cnt / n * 100:.1f}%)")

    cols = [f'ret_{h}d_%' for h in HORIZONS] + ['ret_to_end_%']

    print(f"\n--- breakout-day entry, split by what happened next ---")
    for oc in ('entered', 'failed', 'no_retest'):
        sub = ev[ev['outcome'] == oc]
        print(f"  [{oc}]")
        for c in cols:
            print(f"    breakout_{c:13s} {stats_line(sub['breakout_' + c])}")

    ent = ev[ev['outcome'] == 'entered']
    print(f"\n--- HEAD TO HEAD on the {len(ent)} signals where a retest entry happened ---")
    for c in cols:
        print(f"  {c:14s} breakout: {stats_line(ent['breakout_' + c])}")
        print(f"  {'':14s} retest  : {stats_line(ent['retest_' + c])}")

    if 'days_to_retest' in ent.columns and not ent.empty:
        print(f"\navg days to retest: {ent['days_to_retest'].mean():.1f} "
              f"(median {ent['days_to_retest'].median():.0f})")
    spy = spy_benchmark(as_of)
    if spy is not None:
        print(f"SPY from as-of to end: {spy:+.2f}%")

    os.makedirs('research/output', exist_ok=True)
    out = f"research/output/retest_backtest_{as_of.date()}.csv"
    ev.to_csv(out, index=False)
    print(f"saved: {out}")


if __name__ == '__main__':
    main()
