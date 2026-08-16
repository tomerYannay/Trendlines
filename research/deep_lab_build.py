"""
STAGE 0 of the deep research — enriched long-horizon trade dataset.

Base system: entries = validated rules (upper breakout attempt>=2 / mature
under bounce), stop = line - {1.0, 1.5} x ATR14(entry) projected along the line.
Horizon 90 trading days, NO take-profit — instead, mark-to-market checkpoints
at 20/40/60/90 days so exit rules ("cut if not progressing by day X") can be
designed from the data.

Features add (on top of round-2): MA50/MA200 gaps, MA cross state, SPY 60d
trend and SPY ATR (VIX proxy), price level.

Outputs:
  research/output/deep_lab_dev.csv   (2020-2023  — the ONLY file agents may touch)
  research/output/deep_lab_test.csv  (2024-2026  — locked for the final frozen test)
"""
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import trendline_core as core
from research.build_event_dataset import load, precompute, SEQ_DAYS, EXTREME_PCT, FAIL_PCT
from dashboard.engine import AS_OF, MIN_PRICE, UPPER_MIN_ATTEMPT, UNDER_MIN_LINE_AGE, UNDER_MAX_SLOPE

STOPS = {'s10': 1.0, 's15': 1.5}
HORIZON = 90
CHECKPOINTS = [20, 40, 60, 90]
DEV_END = pd.Timestamp('2023-12-31')


def spy_features():
    rows = db.fetch_query("SELECT date, high, low, close FROM stock_prices WHERE ticker='SPY' ORDER BY date;")
    s = pd.DataFrame(rows, columns=['date', 'high', 'low', 'close'])
    for c_ in ('high', 'low', 'close'):
        s[c_] = s[c_].astype(float)
    prev = s['close'].shift(1)
    tr = pd.concat([s['high'] - s['low'], (s['high'] - prev).abs(), (s['low'] - prev).abs()], axis=1).max(axis=1)
    out = pd.DataFrame({
        'spy_ret_20d': (s['close'] / s['close'].shift(20) - 1) * 100,
        'spy_ret_60d': (s['close'] / s['close'].shift(60) - 1) * 100,
        'spy_above_ma200': (s['close'] > s['close'].rolling(200).mean()).astype(float),
        'spy_atr_pct': tr.rolling(14).mean() / s['close'] * 100,
    })
    out.index = s['date'].astype(str)
    return out


def trade_outcomes(t, i2, p2, slope, h, l, c, atr_abs):
    """Per stop variant: stop info + checkpoint marks + MFE/MAE over 90d."""
    entry = c[t]
    n = len(c)
    out = {}
    for sk, mult in STOPS.items():
        stop_day, stop_ret = None, None
        for u in range(t + 1, min(n, t + 1 + HORIZON)):
            line_u = float(np.exp(np.log(p2) + slope * (u - i2)))
            stop_lvl = line_u - mult * atr_abs
            if stop_lvl > 0 and l[u] <= stop_lvl:
                stop_day, stop_ret = u - t, round((stop_lvl / entry - 1) * 100, 2)
                break
        out[f'{sk}_stop_day'] = stop_day
        out[f'{sk}_stop_ret'] = stop_ret
        for cp in CHECKPOINTS:
            u = t + cp
            if stop_day is not None and stop_day <= cp:
                out[f'{sk}_ret_cp{cp}'] = stop_ret          # already stopped by then
            elif u < n:
                out[f'{sk}_ret_cp{cp}'] = round((c[u] / entry - 1) * 100, 2)
            else:
                out[f'{sk}_ret_cp{cp}'] = None
    w_end = min(n, t + 1 + HORIZON)
    if t + 1 < w_end:
        out['mfe_90d'] = round((h[t + 1:w_end].max() / entry - 1) * 100, 2)
        out['mae_90d'] = round((l[t + 1:w_end].min() / entry - 1) * 100, 2)
        out['peak_day'] = int(np.argmax(h[t + 1:w_end]) + 1)
    return out


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
    delta = pd.Series(c).diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi14 = (100 - 100 / (1 + gain / loss.replace(0, np.nan))).values
    hi52 = pd.Series(h).rolling(252, min_periods=60).max().values
    lo52 = pd.Series(l).rolling(252, min_periods=60).min().values
    ma50 = pd.Series(c).rolling(50).mean().values
    ma200 = pd.Series(c).rolling(200).mean().values
    rows = []

    def emit(t, side, line_t, i2_, p2_, slope_, extra):
        atr_abs = atr14[t] if atr14[t] and not np.isnan(atr14[t]) else c[t] * 0.03
        res = trade_outcomes(t, i2_, p2_, slope_, h, l, c, atr_abs)
        if res.get('s10_ret_cp20') is None:
            return
        rows.append({
            'ticker': ticker, 'side': side, 'event_date': dates[t], 'entry': round(c[t], 2),
            'gap_vs_line_pct': round((c[t] / line_t - 1) * 100, 2),
            'slope_yr_pct': round((np.exp(slope_ * 252) - 1) * 100, 1),
            'days_since_anchor': t - i2_,
            'vol_ratio20': round(v[t] / vol20[t], 2) if vol20[t] and vol20[t] > 0 else None,
            'atr_pct': round(atr14[t] / c[t] * 100, 2) if atr14[t] and c[t] > 0 else None,
            'runup_20d': round(runup20[t], 2) if not np.isnan(runup20[t]) else None,
            'dist_from_ath_pct': round((c[t] / ath[t] - 1) * 100, 2),
            'dist_hi_52w_pct': round((c[t] / hi52[t] - 1) * 100, 2) if not np.isnan(hi52[t]) else None,
            'dist_lo_52w_pct': round((c[t] / lo52[t] - 1) * 100, 2) if not np.isnan(lo52[t]) else None,
            'rsi14': round(rsi14[t], 1) if not np.isnan(rsi14[t]) else None,
            'dollar_vol_m': round(c[t] * vol20[t] / 1e6, 2) if vol20[t] else None,
            'price': round(c[t], 2),
            'ma50_gap_pct': round((c[t] / ma50[t] - 1) * 100, 2) if not np.isnan(ma50[t]) else None,
            'ma200_gap_pct': round((c[t] / ma200[t] - 1) * 100, 2) if not np.isnan(ma200[t]) else None,
            'ma50_vs_ma200_pct': round((ma50[t] / ma200[t] - 1) * 100, 2)
                if not (np.isnan(ma50[t]) or np.isnan(ma200[t])) else None,
            **extra, **res,
        })

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
                emit(t, 'upper', line_t, i2, p2, slope, {'attempt_no': attempt + 1, 'touch_no': None})
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
                emit(t, 'under', line_t, j2, q2, slope_u, {'attempt_no': None, 'touch_no': touch})
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
    print(f"deep lab build: {len(tickers)} tickers, horizon {HORIZON}d, checkpoints {CHECKPOINTS}")
    rows = []
    for i, t in enumerate(tickers, 1):
        try:
            rows.extend(analyze(t))
        except Exception as e:
            print(f"  err {t}: {e}")
        if i % 300 == 0:
            print(f"  ...{i}/{len(tickers)} ({len(rows)})")

    tr = pd.DataFrame(rows)
    tr['event_date'] = pd.to_datetime(tr['event_date'])
    tr['attempt_or_touch'] = tr['attempt_no'].fillna(tr['touch_no'])
    spy = spy_features()
    tr['dkey'] = tr['event_date'].dt.date.astype(str)
    tr = tr.join(spy, on='dkey').drop(columns=['dkey'])

    dev = tr[tr['event_date'] <= DEV_END]
    test = tr[tr['event_date'] > DEV_END]
    dev.to_csv('research/output/deep_lab_dev.csv', index=False)
    test.to_csv('research/output/deep_lab_test.csv', index=False)
    print(f"DONE: DEV {len(dev)} trades (2020-2023) | TEST {len(test)} trades (2024+, locked)")


if __name__ == '__main__':
    main()
