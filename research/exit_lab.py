"""
STAGE 1 — Exit lab: build the master trade dataset for the line-stop system.

For every rule-eligible signal from 2020 onward (upper breakout attempt>=2,
mature under bounce — the validated entry rules, no ML gate):

  STOP  : 5% below the line in force at entry, PROJECTED forward along the
          line's slope (thesis invalidation — the same level that resets the
          diagonal). Intraday touch fills at the stop level; SL precedence.
  TP    : evaluated in PARALLEL for every variant —
          fixed 10/15/20/30/40%, ATR-based 2x/3x/4x ATR14, and none.
  TIME  : max holding 60 trading days (per-ticker bars).

One row per signal with all entry features and one outcome column set per
TP variant.  Discovery must use ONLY period == 'DEV' (exit <= 2023-12-31);
2024+ is reserved for the stage-3 out-of-sample test.

Output: research/output/exit_lab_trades.csv
Usage : python -m research.exit_lab
"""
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import trendline_core as core
from research.build_event_dataset import load, precompute, SEQ_DAYS, EXTREME_PCT, FAIL_PCT
from dashboard.engine import AS_OF, MIN_PRICE, UPPER_MIN_ATTEMPT, UNDER_MIN_LINE_AGE, UNDER_MAX_SLOPE

STOP_BELOW_LINE = 0.05          # stop level: line * (1 - 5%)
HORIZON = 60                    # max holding, trading days (ticker bars)
TP_FIXED = [10, 15, 20, 30, 40]
TP_ATR = [2, 3, 4]
DEV_END = pd.Timestamp('2023-12-31')


def outcomes_for_trade(t, i2, p2, slope, h, l, c, atr_abs):
    """Simulates all exit variants at once for one entry at bar t (entry = close[t])."""
    entry = c[t]
    n = len(c)
    tps = {f'tp{p}': entry * (1 + p / 100) for p in TP_FIXED}
    tps.update({f'atr{k}x': entry + k * atr_abs for k in TP_ATR})
    tps['none'] = None
    results = {k: None for k in tps}

    for u in range(t + 1, min(n, t + 1 + HORIZON)):
        line_u = float(np.exp(np.log(p2) + slope * (u - i2)))
        stop_lvl = line_u * (1 - STOP_BELOW_LINE)
        stop_hit = l[u] <= stop_lvl
        for key, tp_lvl in tps.items():
            if results[key] is not None:
                continue
            if stop_hit:                                   # SL precedence
                results[key] = (round((stop_lvl / entry - 1) * 100, 2), u - t, 'SL')
            elif tp_lvl is not None and h[u] >= tp_lvl:
                results[key] = (round((tp_lvl / entry - 1) * 100, 2), u - t, 'TP')
        if all(v is not None for v in results.values()):
            break

    last_u = min(n - 1, t + HORIZON)
    for key in tps:
        if results[key] is None:
            if last_u > t:
                results[key] = (round((c[last_u] / entry - 1) * 100, 2), last_u - t, 'TIME')
            else:
                results[key] = (None, 0, 'OPEN')
    return results


def analyze(ticker):
    df = load(ticker)
    if df is None or len(df) < 100:
        return []
    dates = df['date'].tolist()
    n = len(df)
    hist_n = max(sum(1 for d in dates if pd.Timestamp(d) < AS_OF), 80)
    if hist_n >= n:
        return []
    h, l, c, v = df['high'].values, df['low'].values, df['close'].values, df['volume'].values
    atr14, vol20, ath, runup20 = precompute(df)
    # extra features: RSI14 (Wilder), 52-week high/low distances, all-time-low distance
    delta = pd.Series(c).diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi14 = (100 - 100 / (1 + gain / loss.replace(0, np.nan))).values
    hi52 = pd.Series(h).rolling(252, min_periods=60).max().values
    lo52 = pd.Series(l).rolling(252, min_periods=60).min().values
    atl = np.minimum.accumulate(l)
    rows = []

    def features(t, i2_, slope_):
        return {
            'gap_vs_line_pct': None,  # filled by caller with line value
            'slope_yr_pct': round((np.exp(slope_ * 252) - 1) * 100, 1),
            'days_since_anchor': t - i2_,
            'vol_ratio20': round(v[t] / vol20[t], 2) if vol20[t] and vol20[t] > 0 else None,
            'atr_pct': round(atr14[t] / c[t] * 100, 2) if atr14[t] and c[t] > 0 else None,
            'runup_20d': round(runup20[t], 2) if not np.isnan(runup20[t]) else None,
            'dist_from_ath_pct': round((c[t] / ath[t] - 1) * 100, 2),
            'dollar_vol_m': round(c[t] * vol20[t] / 1e6, 2) if vol20[t] else None,
            'rsi14': round(rsi14[t], 1) if not np.isnan(rsi14[t]) else None,
            'dist_hi_52w_pct': round((c[t] / hi52[t] - 1) * 100, 2) if not np.isnan(hi52[t]) else None,
            'dist_lo_52w_pct': round((c[t] / lo52[t] - 1) * 100, 2) if not np.isnan(lo52[t]) else None,
            'dist_from_atl_pct': round((c[t] / atl[t] - 1) * 100, 2) if atl[t] > 0 else None,
        }

    def emit(t, side, line_t, i2_, p2_, slope_, extra):
        atr_abs = atr14[t] if atr14[t] and not np.isnan(atr14[t]) else c[t] * 0.03
        res = outcomes_for_trade(t, i2_, p2_, slope_, h, l, c, atr_abs)
        if res['tp20'][0] is None:
            return
        row = {'ticker': ticker, 'side': side, 'event_date': dates[t], 'entry': round(c[t], 2),
               'line': round(line_t, 2), **features(t, i2_, slope_), **extra}
        row['gap_vs_line_pct'] = round((c[t] / line_t - 1) * 100, 2)
        for key, (ret, days, reason) in res.items():
            row[f'ret_{key}'] = ret
            row[f'days_{key}'] = days
            row[f'why_{key}'] = reason
        rows.append(row)

    # ---- upper ----
    up = core.best_upper_trendline(h[:hist_n])
    if up is not None:
        i1, i2, slope = up
        p2 = h[i2]
        seq, attempt, had_bt = 0, 0, False
        for t in range(hist_n, n):
            line_t = float(np.exp(np.log(p2) + slope * (t - i2)))
            bt = c[t] > line_t
            if bt:
                had_bt = True
            dist = (line_t - c[t]) / c[t] * 100
            s = seq + 1 if bt else 0
            if bt and seq == 0 and c[t] >= MIN_PRICE and attempt + 1 >= UPPER_MIN_ATTEMPT:
                emit(t, 'upper', line_t, i2, p2, slope, {'attempt_no': attempt + 1})
            if bt and seq == 0:
                attempt += 1
            flag = (s > SEQ_DAYS) or (had_bt and dist > FAIL_PCT) or (dist < -EXTREME_PCT)
            seq = s
            if flag:
                r = core.best_upper_trendline(h[:t + 1])
                if r is not None:
                    i1, i2, slope = r
                    p2 = h[i2]
                    seq, attempt, had_bt = 0, 0, False

    # ---- under ----
    un = core.best_under_trendline(l[:hist_n])
    if un is not None:
        j1, j2, slope_u = un
        q2 = l[j2]
        seq, touch, last_touch = 0, 0, -10**9
        for t in range(hist_n, n):
            line_t = float(np.exp(np.log(q2) + slope_u * (t - j2)))
            bt = c[t] < line_t
            dist = (line_t - c[t]) / c[t] * 100
            s = seq + 1 if bt else 0
            if (l[t] <= line_t and c[t] > line_t and t - last_touch > 3
                    and c[t] >= MIN_PRICE and (t - j2) >= UNDER_MIN_LINE_AGE
                    and abs((np.exp(slope_u * 252) - 1) * 100) <= UNDER_MAX_SLOPE):
                touch += 1
                emit(t, 'under', line_t, j2, q2, slope_u, {'touch_no': touch})
            elif l[t] <= line_t and t - last_touch > 3:
                touch += 1
            if l[t] <= line_t and t - last_touch > 3:
                last_touch = t
            flag = (s > SEQ_DAYS) or (dist > 0 and seq > 0 and s == 0) or (dist > EXTREME_PCT)
            seq = s
            if flag:
                r = core.best_under_trendline(l[:t + 1])
                if r is not None:
                    j1, j2, slope_u = r
                    q2 = l[j2]
                    seq, touch, last_touch = 0, 0, -10**9

    return rows


def main():
    db.cursor.execute("SELECT ticker FROM tickers_russell ORDER BY ticker;")
    tickers = [r[0] for r in db.cursor.fetchall()]
    print(f"exit lab: {len(tickers)} tickers, stop = line - {STOP_BELOW_LINE*100:.0f}%, horizon {HORIZON}d")

    all_rows = []
    for i, t in enumerate(tickers, 1):
        try:
            all_rows.extend(analyze(t))
        except Exception as e:
            print(f"  err {t}: {e}")
        if i % 300 == 0:
            print(f"  ...{i}/{len(tickers)} ({len(all_rows)} trades)")

    tr = pd.DataFrame(all_rows)
    tr['period'] = np.where(pd.to_datetime(tr['event_date']) <= DEV_END, 'DEV', 'TEST')
    tr.to_csv('research/output/exit_lab_trades.csv', index=False)
    print(f"\nsaved {len(tr)} trades -> research/output/exit_lab_trades.csv")
    print(tr.groupby(['period', 'side']).size())

    # quick stage-1 summary: DEV-period expectancy per TP variant
    dev = tr[tr['period'] == 'DEV']
    print("\n=== DEV period (2020-2023) — expectancy per TP variant ===")
    print(f"{'variant':8s} {'side':6s} {'n':>6s} {'win%':>7s} {'avg%':>7s} {'med%':>7s} {'avg days':>9s}")
    for key in [f'tp{p}' for p in TP_FIXED] + [f'atr{k}x' for k in TP_ATR] + ['none']:
        for side in ('upper', 'under'):
            d = dev[dev['side'] == side]
            r = d[f'ret_{key}'].dropna()
            if len(r) == 0:
                continue
            print(f"{key:8s} {side:6s} {len(r):>6d} {(r > 0).mean() * 100:>6.1f}% {r.mean():>+6.2f}% "
                  f"{r.median():>+6.2f}% {d[f'days_{key}'].mean():>8.1f}")


if __name__ == '__main__':
    main()
