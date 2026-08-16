"""
Build the master event dataset for scenario research.

Runs the live walk-forward simulation once (persistent lines: shallow failed
breakouts do NOT re-anchor; renewal only on seq>200 / 100% extreme / deep
failure >5% below the line) and records EVERY event with rich features and
outcomes, so that any scenario can later be evaluated as a cheap filter over
one table.

Events:
  upper_breakout : every fresh close above the upper line in force
  under_touch    : every day the low touches/pierces the support line
                   (close above OR below recorded — the filter decides later)

Output: research/output/event_dataset_<asof>.csv

Usage:
    python -m research.build_event_dataset --as-of 2025-07-01
"""
import argparse
import os
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import trendline_core as core

SEQ_DAYS = 200
EXTREME_PCT = 100.0
FAIL_PCT = 5.0
FWD = [5, 10, 20, 40]


def load(ticker):
    rows = db.fetch_query("""
        SELECT date, high, low, close, volume FROM stock_prices
        WHERE ticker = %s ORDER BY date;
    """, (ticker,))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=['date', 'high', 'low', 'close', 'volume'])
    for c in ('high', 'low', 'close', 'volume'):
        df[c] = df[c].astype(float)
    return df


def precompute(df):
    """Vectorized per-ticker context features."""
    h, l, c, v = df['high'].values, df['low'].values, df['close'].values, df['volume'].values
    n = len(df)
    prev_c = np.roll(c, 1); prev_c[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr14 = pd.Series(tr).rolling(14).mean().values
    vol20 = pd.Series(v).rolling(20).mean().values
    ath = np.maximum.accumulate(h)
    runup20 = np.full(n, np.nan)
    runup20[20:] = (c[20:] / c[:-20] - 1) * 100
    return atr14, vol20, ath, runup20


def outcomes(c, h, l, t, line_fn):
    """Forward returns, MFE/MAE within 20d, and stop info (first close below the line)."""
    out = {}
    n = len(c)
    for hz in FWD:
        out[f'ret_{hz}d'] = round((c[t + hz] / c[t] - 1) * 100, 2) if t + hz < n else None
    out['ret_end'] = round((c[-1] / c[t] - 1) * 100, 2) if t < n - 1 else None
    w_end = min(n, t + 21)
    if t + 1 < w_end:
        out['mfe_20d'] = round((h[t + 1:w_end].max() / c[t] - 1) * 100, 2)
        out['mae_20d'] = round((l[t + 1:w_end].min() / c[t] - 1) * 100, 2)
    else:
        out['mfe_20d'] = out['mae_20d'] = None
    # stop: first close below the line within 20d
    stop_day, stop_ret = None, None
    for u in range(t + 1, w_end):
        if c[u] < line_fn(u):
            stop_day, stop_ret = u - t, round((c[u] / c[t] - 1) * 100, 2)
            break
    out['stop_day'] = stop_day
    out['ret_at_stop'] = stop_ret
    return out


def analyze(ticker, as_of, until=None, min_price=2.0):
    df = load(ticker)
    if df is None or len(df) < 80:
        return []
    dates = df['date'].tolist()
    n = len(df)
    hist_n = sum(1 for d in dates if pd.Timestamp(d) < as_of)
    if hist_n < 80 or hist_n == n:
        return []
    # events are detected only inside [as_of, until); outcomes may use later data
    until_n = n if until is None else sum(1 for d in dates if pd.Timestamp(d) < until)
    if until_n <= hist_n:
        return []

    h, l, c, v = df['high'].values, df['low'].values, df['close'].values, df['volume'].values
    atr14, vol20, ath, runup20 = precompute(df)
    events = []

    def base_features(t, side, line_t, slope, i2, extra):
        return {
            'ticker': ticker, 'side': side, 'event_date': dates[t],
            'close': round(c[t], 2), 'line': round(line_t, 2),
            'gap_vs_line_pct': round((c[t] / line_t - 1) * 100, 2),
            'slope_yr_pct': round((np.exp(slope * 252) - 1) * 100, 1),
            'days_since_anchor': t - i2,
            'vol_ratio20': round(v[t] / vol20[t], 2) if vol20[t] and vol20[t] > 0 else None,
            'atr_pct': round(atr14[t] / c[t] * 100, 2) if atr14[t] and c[t] > 0 else None,
            'runup_20d': round(runup20[t], 2) if not np.isnan(runup20[t]) else None,
            'dist_from_ath_pct': round((c[t] / ath[t] - 1) * 100, 2),
            'dollar_vol_m': round(c[t] * vol20[t] / 1e6, 2) if vol20[t] else None,
            **extra,
        }

    # ---------------- UPPER ----------------
    up = core.best_upper_trendline(h[:hist_n])
    if up is not None:
        i2, p2, slope = up[1], h[up[1]], up[2]
        seq, attempt, had_breakout = 0, 0, False
        for t in range(hist_n, until_n):
            line_t = float(np.exp(np.log(p2) + slope * (t - i2)))
            bt = c[t] > line_t
            if bt:
                had_breakout = True
            dist = (line_t - c[t]) / c[t] * 100
            s = seq + 1 if bt else 0

            if bt and seq == 0 and c[t] >= min_price:
                attempt += 1
                lf = (lambda i2_, p2_, sl_: lambda u: float(np.exp(np.log(p2_) + sl_ * (u - i2_))))(i2, p2, slope)
                events.append(base_features(t, 'upper_breakout', line_t, slope, i2,
                                            {'attempt_no': attempt, **outcomes(c, h, l, t, lf)}))

            # deep failure: after ANY breakout on this line, a close >FAIL_PCT below it resets
            flag = (s > SEQ_DAYS) or (had_breakout and dist > FAIL_PCT) or (dist < -EXTREME_PCT)
            seq = s
            if flag:
                res = core.best_upper_trendline(h[:t + 1])
                if res is not None:
                    i2, p2, slope = res[1], h[res[1]], res[2]
                    seq, attempt, had_breakout = 0, 0, False

    # ---------------- UNDER ----------------
    un = core.best_under_trendline(l[:hist_n])
    if un is not None:
        j2, q2, slope_u = un[1], l[un[1]], un[2]
        seq, prev_bt, touch = 0, False, 0
        last_touch_t = -10**9
        for t in range(hist_n, until_n):
            line_t = float(np.exp(np.log(q2) + slope_u * (t - j2)))
            bt = c[t] < line_t
            dist = (line_t - c[t]) / c[t] * 100
            s = seq + 1 if bt else 0

            # touch event: low reaches the line (new touch only after 3 clear days)
            if l[t] <= line_t and c[t] >= min_price and t - last_touch_t > 3:
                touch += 1
                lf = (lambda j2_, q2_, sl_: lambda u: float(np.exp(np.log(q2_) + sl_ * (u - j2_))))(j2, q2, slope_u)
                events.append(base_features(t, 'under_touch', line_t, slope_u, j2, {
                    'touch_no': touch,
                    'pierce_depth_pct': round((line_t - l[t]) / line_t * 100, 2),
                    'closed_above': bool(c[t] > line_t),
                    **outcomes(c, h, l, t, lf),
                }))
                last_touch_t = t

            flag = (s > SEQ_DAYS) or (dist > 0 and prev_bt) or (dist > EXTREME_PCT)
            seq, prev_bt = s, bt
            if flag:
                res = core.best_under_trendline(l[:t + 1])
                if res is not None:
                    j2, q2, slope_u = res[1], l[res[1]], res[2]
                    seq, prev_bt, touch = 0, False, 0
                    last_touch_t = -10**9

    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-of', default='2025-07-01')
    ap.add_argument('--until', default=None, help='detect events only before this date (outcomes may extend past it)')
    args = ap.parse_args()
    as_of = pd.Timestamp(args.as_of)
    until = pd.Timestamp(args.until) if args.until else None

    db.cursor.execute("SELECT ticker FROM tickers_russell ORDER BY ticker;")
    tickers = [r[0] for r in db.cursor.fetchall()]
    print(f"building event dataset | as-of {as_of.date()} | {len(tickers)} tickers")

    all_events = []
    for i, t in enumerate(tickers, 1):
        try:
            all_events.extend(analyze(t, as_of, until=until))
        except Exception as e:
            print(f"  error {t}: {e}")
        if i % 300 == 0:
            print(f"  ...{i}/{len(tickers)} ({len(all_events)} events)")

    ev = pd.DataFrame(all_events)
    os.makedirs('research/output', exist_ok=True)
    suffix = f"_{until.date()}" if until else ""
    out = f"research/output/event_dataset_{as_of.date()}{suffix}.csv"
    ev.to_csv(out, index=False)
    print(f"DONE: {len(ev)} events ({(ev['side'] == 'upper_breakout').sum()} upper, "
          f"{(ev['side'] == 'under_touch').sum()} under) -> {out}")


if __name__ == '__main__':
    main()
