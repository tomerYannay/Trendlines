"""
Point-in-time diagonal backtest (long-only).

Anchors BOTH diagonals for every ticker using ONLY data up to --as-of
(default 2026-07-01, exclusive), then walks forward candle by candle:

  * mode=dynamic (default): replays the LIVE pipeline — each day the status
    is computed against the line currently in force; when the live update
    rules fire (sequence > 50, failed breakout, distance beyond the extreme
    threshold) the diagonal is re-anchored on all data up to that candle and
    takes effect from the NEXT candle, exactly like the daily flow.
  * mode=static: the lines stay frozen at as-of for the whole period.

Events collected (long-only, no shorts):
  * UPPER (resistance) : BREAKOUT — close crosses above the line in force
  * UNDER (support)    : BOUNCE — low touches/pierces the line in force
                         intraday but the close holds above it

For each event, forward returns from the event close after +5/+10/+20
trading days and to the last date in the DB, plus a SPY benchmark.
Per ticker per side, a new event is only recorded after a 20-trading-day
cooldown (as if the previous position is still open).

Usage (from the project root):
    python -m research.backtest_frozen_diagonals
    python -m research.backtest_frozen_diagonals --mode static
    python -m research.backtest_frozen_diagonals --as-of 2025-07-01 --min-days 50
"""
import argparse
import os
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import trendline_core as core

HORIZONS = [5, 10, 20]


def load_prices(ticker):
    rows = db.fetch_query("""
        SELECT date, high, low, close FROM stock_prices
        WHERE ticker = %s ORDER BY date;
    """, (ticker,))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=['date', 'high', 'low', 'close'])
    for c in ('high', 'low', 'close'):
        df[c] = df[c].astype(float)
    return df


def line_over_full_series(anchor_i2, anchor_price, slope, n):
    return np.exp(np.log(anchor_price) + slope * (np.arange(n) - anchor_i2))


def first_event(mask, start_idx):
    idxs = np.nonzero(mask)[0]
    idxs = idxs[idxs >= start_idx]
    return int(idxs[0]) if len(idxs) else None


def forward_returns(closes, i):
    out = {}
    for h in HORIZONS:
        out[f'ret_{h}d_%'] = round((closes[i + h] / closes[i] - 1) * 100, 2) if i + h < len(closes) else None
    out['ret_to_end_%'] = round((closes[-1] / closes[i] - 1) * 100, 2) if i < len(closes) - 1 else None
    return out


def analyze_ticker(ticker, as_of, min_price):
    df = load_prices(ticker)
    if df is None or len(df) < 60:
        return []

    dates = df['date'].tolist()
    n = len(df)
    hist_n = sum(1 for d in dates if pd.Timestamp(d) < as_of)   # rows strictly before as-of
    if hist_n < 60 or hist_n == n:                              # need history AND an eval window
        return []

    highs, lows, closes = df['high'].values, df['low'].values, df['close'].values
    events = []

    # ---- UPPER: breakout above the frozen resistance line ----
    up = core.best_upper_trendline(highs[:hist_n])
    if up is not None:
        i1, i2, slope = up
        line = line_over_full_series(i2, highs[i2], slope, n)
        above = closes > line
        crossed = above & ~np.roll(above, 1)          # close crossed above vs previous day
        crossed[0] = False
        ev = first_event(crossed, hist_n)
        if ev is not None and closes[ev] >= min_price:
            events.append({
                'ticker': ticker, 'side': 'upper_breakout',
                'event_date': dates[ev], 'event_close': round(closes[ev], 2),
                'line_price': round(line[ev], 2),
                'slope_yr_%': round((np.exp(slope * 252) - 1) * 100, 1),
                'days_since_anchor': ev - i2,
                **forward_returns(closes, ev),
            })

    # ---- UNDER: bounce off the frozen support line (long only) ----
    un = core.best_under_trendline(lows[:hist_n])
    if un is not None:
        j1, j2, slope_u = un
        line_u = line_over_full_series(j2, lows[j2], slope_u, n)
        bounce = (lows <= line_u) & (closes > line_u)
        ev = first_event(bounce, hist_n)
        if ev is not None and closes[ev] >= min_price:
            events.append({
                'ticker': ticker, 'side': 'under_bounce',
                'event_date': dates[ev], 'event_close': round(closes[ev], 2),
                'line_price': round(line_u[ev], 2),
                'slope_yr_%': round((np.exp(slope_u * 252) - 1) * 100, 1),
                'days_since_anchor': ev - j2,
                **forward_returns(closes, ev),
            })

    return events


COOLDOWN = 20  # trading days before another event of the same side is recorded


def analyze_ticker_dynamic(ticker, as_of, min_price, seq_days=50, extreme_pct=20.0, fail_pct=None):
    """
    Walk-forward replay of the live pipeline: status vs the line in force,
    re-anchor when the live update rules fire (new line effective next candle).
    Update rules (mirroring update_upper_status / update_under_status),
    whichever threshold is hit FIRST resets the diagonal:
      upper: seq > seq_days  |  failed breakout  |  distance < -extreme_pct
      under: seq > seq_days  |  (second consecutive close below support) |  distance > +extreme_pct

    fail_pct: controls what counts as a FAILED breakout on the upper side.
      None (live default) -> ANY close back below the line after a breakout
                             re-anchors the diagonal.
      number (e.g. 5)     -> the line survives shallow failures: it is only
                             re-anchored when the close falls more than
                             fail_pct% BELOW the line right after a breakout.
                             Shallow dips keep the same line, and the NEXT
                             breakout of that same line is tracked as
                             attempt #2, #3, ... (attempt_no column).
    Upper breakout events are recorded on every fresh cross (a prior position
    is implicitly closed when the close falls back under the line).
    """
    df = load_prices(ticker)
    if df is None or len(df) < 60:
        return [], 0

    dates = df['date'].tolist()
    n = len(df)
    hist_n = sum(1 for d in dates if pd.Timestamp(d) < as_of)
    if hist_n < 60 or hist_n == n:
        return [], 0

    highs, lows, closes = df['high'].values, df['low'].values, df['close'].values
    events = []
    reanchors = 0

    # ---- initial anchors from data before as-of ----
    up = core.best_upper_trendline(highs[:hist_n])
    up_state = (up[1], highs[up[1]], up[2]) if up else None   # (i2, price2, slope)
    up_seq, up_prev_bt = 0, False
    up_attempt = 0        # breakout attempts on the current line instance

    un = core.best_under_trendline(lows[:hist_n])
    un_state = (un[1], lows[un[1]], un[2]) if un else None
    un_seq, un_prev_bt, last_un_event = 0, False, -10**9

    for t in range(hist_n, n):
        # ---------- UPPER (resistance) ----------
        if up_state is not None:
            i2, p2, slope = up_state
            line_t = float(np.exp(np.log(p2) + slope * (t - i2)))
            bt = closes[t] > line_t
            dist = (line_t - closes[t]) / closes[t] * 100
            seq = up_seq + 1 if bt else 0

            # breakout event: every fresh close above the line in force
            # (previous attempt implicitly exited when the close fell back under)
            if bt and up_seq == 0 and closes[t] >= min_price:
                up_attempt += 1
                events.append({
                    'ticker': ticker, 'side': 'upper_breakout',
                    'event_date': dates[t], 'event_close': round(closes[t], 2),
                    'line_price': round(line_t, 2),
                    'slope_yr_%': round((np.exp(slope * 252) - 1) * 100, 1),
                    'days_since_anchor': t - i2,
                    'attempt_no': up_attempt,
                    **forward_returns(closes, t),
                })

            if fail_pct is None:
                failed_breakout = (dist > 0 and up_prev_bt)          # live rule: any close back below
            else:
                failed_breakout = (dist > fail_pct and up_prev_bt)   # only a DEEP close below kills the line
            update_flag = (seq > seq_days) or failed_breakout or (dist < -extreme_pct)
            up_seq, up_prev_bt = seq, bt
            if update_flag:
                res = core.best_upper_trendline(highs[:t + 1])
                if res is not None:
                    up_state = (res[1], highs[res[1]], res[2])   # effective from next candle
                    up_seq, up_prev_bt = 0, False                # fresh line: nothing above it yet
                    up_attempt = 0
                    reanchors += 1

        # ---------- UNDER (support) ----------
        if un_state is not None:
            j2, q2, slope_u = un_state
            line_t = float(np.exp(np.log(q2) + slope_u * (t - j2)))
            bt = closes[t] < line_t
            dist = (line_t - closes[t]) / closes[t] * 100
            seq = un_seq + 1 if bt else 0

            # bounce event: intraday touch of the line, close holds above (long only)
            if (lows[t] <= line_t and closes[t] > line_t
                    and t - last_un_event > COOLDOWN and closes[t] >= min_price):
                events.append({
                    'ticker': ticker, 'side': 'under_bounce',
                    'event_date': dates[t], 'event_close': round(closes[t], 2),
                    'line_price': round(line_t, 2),
                    'slope_yr_%': round((np.exp(slope_u * 252) - 1) * 100, 1),
                    'days_since_anchor': t - j2,
                    **forward_returns(closes, t),
                })
                last_un_event = t

            update_flag = (seq > seq_days) or (dist > 0 and un_prev_bt) or (dist > extreme_pct)
            un_seq, un_prev_bt = seq, bt
            if update_flag:
                res = core.best_under_trendline(lows[:t + 1])
                if res is not None:
                    un_state = (res[1], lows[res[1]], res[2])
                    un_seq, un_prev_bt = 0, False
                    reanchors += 1

    return events, reanchors


def spy_benchmark(as_of):
    df = load_prices('SPY')
    if df is None:
        return None
    dates = [pd.Timestamp(d) for d in df['date']]
    start = next((i for i, d in enumerate(dates) if d >= as_of), None)
    if start is None:
        return None
    return round((df['close'].iloc[-1] / df['close'].iloc[start] - 1) * 100, 2)


def summarize(df, label, spy):
    print(f"\n{'=' * 70}\n{label}: {len(df)} events\n{'=' * 70}")
    if df.empty:
        return
    for col in [f'ret_{h}d_%' for h in HORIZONS] + ['ret_to_end_%']:
        s = df[col].dropna().astype(float)
        if s.empty:
            continue
        win = (s > 0).mean() * 100
        print(f"  {col:14s} n={len(s):4d}  win-rate={win:5.1f}%  avg={s.mean():+6.2f}%  "
              f"median={s.median():+6.2f}%  best={s.max():+7.2f}%  worst={s.min():+7.2f}%")
    if spy is not None:
        print(f"  benchmark: SPY from as-of to end = {spy:+.2f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-of', default='2026-07-01', help='anchor lines on data BEFORE this date (default 2026-07-01)')
    ap.add_argument('--min-price', type=float, default=2.0, help='minimum event close (default 2.0)')
    ap.add_argument('--min-days', type=int, default=0,
                    help='keep only events where the line is at least this many trading days past its anchor (default 0 = all)')
    ap.add_argument('--mode', choices=['dynamic', 'static'], default='dynamic',
                    help="'dynamic' (default) replays the live re-anchoring rules candle by candle; 'static' freezes the as-of lines")
    ap.add_argument('--seq-days', type=int, default=50,
                    help='re-anchor after this many consecutive closes beyond the line (default 50)')
    ap.add_argument('--extreme-pct', type=float, default=20.0,
                    help='re-anchor when the close is this %% beyond the line (default 20)')
    ap.add_argument('--fail-pct', type=float, default=None,
                    help='upper side: keep the line through shallow failed breakouts; only a close more than '
                         'this %% below the line re-anchors. Omit for the live rule (any close below re-anchors)')
    args = ap.parse_args()

    as_of = pd.Timestamp(args.as_of)
    db.cursor.execute("SELECT ticker FROM tickers_russell ORDER BY ticker;")
    tickers = [r[0] for r in db.cursor.fetchall()]
    print(f"Mode: {args.mode} | anchoring diagonals on data before {as_of.date()} for {len(tickers)} tickers...")

    all_events = []
    total_reanchors = 0
    for i, t in enumerate(tickers, 1):
        try:
            if args.mode == 'dynamic':
                evs, re_n = analyze_ticker_dynamic(t, as_of, args.min_price,
                                                   seq_days=args.seq_days,
                                                   extreme_pct=args.extreme_pct,
                                                   fail_pct=args.fail_pct)
                all_events.extend(evs)
                total_reanchors += re_n
            else:
                all_events.extend(analyze_ticker(t, as_of, args.min_price))
        except Exception as e:
            print(f"  error {t}: {e}")
        if i % 400 == 0:
            print(f"  ...{i}/{len(tickers)}")

    if args.mode == 'dynamic':
        print(f"re-anchor events during the walk-forward: {total_reanchors}")

    ev = pd.DataFrame(all_events)
    if ev.empty:
        print("No events found.")
        return

    if args.min_days:
        before = len(ev)
        ev = ev[ev['days_since_anchor'] >= args.min_days]
        print(f"maturity filter (days_since_anchor >= {args.min_days}): {before} -> {len(ev)} events")

    spy = spy_benchmark(as_of)
    summarize(ev[ev['side'] == 'upper_breakout'], f"UPPER BREAKOUTS since {as_of.date()}", spy)

    # breakdown by attempt number on the same line instance
    up_ev = ev[ev['side'] == 'upper_breakout']
    if 'attempt_no' in up_ev.columns and not up_ev.empty:
        print("\n--- upper breakouts by attempt number on the SAME line ---")
        buckets = [(1, '1st'), (2, '2nd'), (3, '3rd')]
        for no, name in buckets:
            summarize(up_ev[up_ev['attempt_no'] == no], f"attempt {name}", None)
        summarize(up_ev[up_ev['attempt_no'] >= 4], "attempt 4th+", None)

    summarize(ev[ev['side'] == 'under_bounce'], f"UNDER BOUNCES since {as_of.date()}", spy)

    os.makedirs('research/output', exist_ok=True)
    out = f"research/output/diagonal_events_{args.mode}_{as_of.date()}.csv"
    ev.sort_values(['side', 'ret_to_end_%'], ascending=[True, False]).to_csv(out, index=False)
    print(f"\nfull event list saved: {out}")

    # top performers per side
    for side in ('upper_breakout', 'under_bounce'):
        top = ev[ev['side'] == side].nlargest(10, 'ret_to_end_%')
        if not top.empty:
            print(f"\ntop 10 {side} by return to end:")
            print(top[['ticker', 'event_date', 'event_close', 'slope_yr_%',
                       'days_since_anchor', 'ret_5d_%', 'ret_to_end_%']].to_string(index=False))


if __name__ == '__main__':
    main()
