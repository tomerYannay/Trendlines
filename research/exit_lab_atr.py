"""
Exit lab round 2 — ATR-buffered line stop.

STOP grid : line - {1.0, 1.5, 2.0} x ATR14(entry), projected along the line
TP grid   : none, +20%, +40%, 3xATR, 4xATR
Horizon   : 60 trading days
Protocol  : identical to round 1 — policy/model/threshold chosen on DEV
            (2020-2023) only, then frozen and applied to TEST (2024-2026).

Usage:  python -m research.exit_lab_atr
"""
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import trendline_core as core
from research.build_event_dataset import load, precompute, SEQ_DAYS, EXTREME_PCT, FAIL_PCT
from dashboard.engine import AS_OF, MIN_PRICE, UPPER_MIN_ATTEMPT, UNDER_MIN_LINE_AGE, UNDER_MAX_SLOPE
from research.confidence import make_bins, bin_index, woe_table, fit_logistic, spy_context

STOPS = {'s10': 1.0, 's15': 1.5, 's20': 2.0}          # ATR multiples below the line
TPS = {'none': None, 'tp20': 20, 'tp40': 40, 'atr3x': 3, 'atr4x': 4}
HORIZON = 60
DEV_END = pd.Timestamp('2023-12-31')
FEATS = ['attempt_or_touch', 'days_since_anchor', 'slope_yr_pct', 'vol_ratio20', 'atr_pct',
         'runup_20d', 'dist_from_ath_pct', 'dist_hi_52w_pct', 'dist_lo_52w_pct', 'rsi14',
         'dollar_vol_m', 'gap_vs_line_pct', 'spy_ret_20d', 'spy_above_ma200']


def combo_keys():
    return [f"{sk}_{tk}" for sk in STOPS for tk in TPS]


def outcomes_for_trade(t, i2, p2, slope, side_sign, h, l, c, atr_abs):
    """side_sign: -1 for upper (stop below a declining line), -1 for under too —
    stop is always BELOW the line for long trades on either side."""
    entry = c[t]
    n = len(c)
    tp_lvls = {}
    for tk, v in TPS.items():
        if v is None:
            tp_lvls[tk] = None
        elif tk.startswith('tp'):
            tp_lvls[tk] = entry * (1 + v / 100)
        else:
            tp_lvls[tk] = entry + v * atr_abs
    results = {k: None for k in combo_keys()}

    for u in range(t + 1, min(n, t + 1 + HORIZON)):
        line_u = float(np.exp(np.log(p2) + slope * (u - i2)))
        for sk, mult in STOPS.items():
            stop_lvl = line_u - mult * atr_abs
            stop_hit = l[u] <= stop_lvl and stop_lvl > 0
            for tk, tp_lvl in tp_lvls.items():
                key = f"{sk}_{tk}"
                if results[key] is not None:
                    continue
                if stop_hit:
                    results[key] = (round((stop_lvl / entry - 1) * 100, 2), u - t, 'SL')
                elif tp_lvl is not None and h[u] >= tp_lvl:
                    results[key] = (round((tp_lvl / entry - 1) * 100, 2), u - t, 'TP')
        if all(v is not None for v in results.values()):
            break

    last_u = min(n - 1, t + HORIZON)
    for key in results:
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
    delta = pd.Series(c).diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi14 = (100 - 100 / (1 + gain / loss.replace(0, np.nan))).values
    hi52 = pd.Series(h).rolling(252, min_periods=60).max().values
    lo52 = pd.Series(l).rolling(252, min_periods=60).min().values
    rows = []

    def emit(t, side, line_t, i2_, p2_, slope_, extra):
        atr_abs = atr14[t] if atr14[t] and not np.isnan(atr14[t]) else c[t] * 0.03
        res = outcomes_for_trade(t, i2_, p2_, slope_, -1, h, l, c, atr_abs)
        if res['s15_tp20'][0] is None:
            return
        row = {'ticker': ticker, 'side': side, 'event_date': dates[t], 'entry': round(c[t], 2),
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
               **extra}
        for key, (ret, days, reason) in res.items():
            row[f'ret_{key}'] = ret
            row[f'days_{key}'] = days
        rows.append(row)

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


def build():
    db.cursor.execute("SELECT ticker FROM tickers_russell ORDER BY ticker;")
    tickers = [r[0] for r in db.cursor.fetchall()]
    print(f"ATR-stop lab: {len(tickers)} tickers | stops {list(STOPS.values())}xATR below line | {len(combo_keys())} exit combos")
    rows = []
    for i, t in enumerate(tickers, 1):
        try:
            rows.extend(analyze(t))
        except Exception as e:
            print(f"  err {t}: {e}")
        if i % 300 == 0:
            print(f"  ...{i}/{len(tickers)} ({len(rows)})")
    tr = pd.DataFrame(rows)
    tr.to_csv('research/output/exit_lab_atr_trades.csv', index=False)
    print(f"saved {len(tr)} trades")
    return tr


def study(tr):
    tr['event_date'] = pd.to_datetime(tr['event_date'])
    tr['attempt_or_touch'] = tr['attempt_no'].fillna(tr['touch_no'])
    spy = spy_context()
    tr['dkey'] = tr['event_date'].dt.date.astype(str)
    tr = tr.join(spy, on='dkey')
    dev = tr[tr['event_date'] <= DEV_END].copy()
    mid = dev['event_date'].median()

    print("\n=== A. exit-combo selection (DEV 2020-2023) ===")
    choice = {}
    for side in ('upper', 'under'):
        d = dev[dev['side'] == side]
        rows = []
        for key in combo_keys():
            r = d[f'ret_{key}'].dropna()
            h1 = d[d['event_date'] < mid][f'ret_{key}'].dropna()
            h2 = d[d['event_date'] >= mid][f'ret_{key}'].dropna()
            rows.append((key, len(r), (r > 0).mean() * 100, r.mean(), r.median(), h1.mean(), h2.mean()))
        rows.sort(key=lambda x: -x[3])
        print(f"\n[{side}] top 6 combos:  combo | n | win% | avg% | med% | h1 | h2")
        for key, nn, wn, av, md, h1, h2 in rows[:6]:
            print(f"  {key:11s} n={nn:5d} win={wn:5.1f}% avg={av:+6.2f}% med={md:+6.2f}%  h1={h1:+.2f}% h2={h2:+.2f}%")
        best = next((k for k, nn, wn, av, md, h1, h2 in rows if h1 > 0 and h2 > 0), rows[0][0])
        choice[side] = best
        print(f"  -> chosen for {side}: {best}")

    # model: fit 2020-2022, calibrate 2023
    calib_start = pd.Timestamp('2023-01-01')
    model = {}
    for side in ('upper', 'under'):
        d = dev[dev['side'] == side].copy()
        col = f"ret_{choice[side]}"
        d = d[d[col].notna()]
        d['y'] = (d[col] > 0).astype(float)
        fit_set, cal_set = d[d['event_date'] < calib_start], d[d['event_date'] >= calib_start]
        base = fit_set['y'].mean()
        feats, X_cols = {}, []
        for f in FEATS:
            x = fit_set[f].astype(float).values
            edges = make_bins(x)
            idx = bin_index(x, edges)
            woe = woe_table(idx, fit_set['y'].values, len(edges) + 1, base)
            feats[f] = {'edges': edges, 'woe': woe}
            X_cols.append(np.where(idx < 0, 0.0, np.array(woe)[np.clip(idx, 0, len(woe) - 1)]))
        w = fit_logistic(np.column_stack(X_cols), fit_set['y'].values)
        m = {'features': feats, 'w': w}

        def raw_p(frame, m=m):
            cols = []
            for f, spec in m['features'].items():
                x = frame[f].astype(float).values
                idx = bin_index(x, spec['edges'])
                woe = np.array(spec['woe'])
                cols.append(np.where(idx < 0, 0.0, woe[np.clip(idx, 0, len(woe) - 1)]))
            X = np.column_stack(cols)
            wv = np.array(m['w'])
            return 1 / (1 + np.exp(-(wv[0] + X @ wv[1:])))

        p_cal = raw_p(cal_set)
        qs = np.quantile(p_cal, np.linspace(0, 1, 11))
        curve = []
        for i in range(10):
            msk = (p_cal >= qs[i]) & (p_cal < qs[i + 1] if i < 9 else p_cal <= qs[i + 1])
            if msk.sum():
                curve.append((float(p_cal[msk].mean()), float(cal_set['y'].values[msk].mean())))
        m['curve'] = curve
        m['raw_p'] = raw_p
        model[side] = m

    def conf(frame, side):
        m = model[side]
        p = m['raw_p'](frame)
        xs = np.array([c0 for c0, _ in m['curve']]); ys = np.array([c1 for _, c1 in m['curve']])
        return np.interp(p, xs, ys) * 100

    for frame in (dev, tr):
        for side in ('upper', 'under'):
            msk = frame['side'] == side
            frame.loc[msk, 'conf'] = conf(frame[msk], side)
        frame['ret_chosen'] = np.where(frame['side'] == 'upper',
                                       frame[f"ret_{choice['upper']}"], frame[f"ret_{choice['under']}"])
        frame['days_chosen'] = np.where(frame['side'] == 'upper',
                                        frame[f"days_{choice['upper']}"], frame[f"days_{choice['under']}"])

    print("\n=== B. threshold X (DEV) ===")
    best_x, best_avg = None, -1e9
    for p in (50, 60, 70, 80, 90):
        x = round(float(np.percentile(dev['conf'].dropna(), p)), 1)
        g = dev[dev['conf'] >= x]['ret_chosen'].dropna()
        if len(g) < 300:
            continue
        print(f"  X={x}: n={len(g):5d}  win={(g > 0).mean()*100:5.1f}%  avg={g.mean():+6.2f}%")
        if g.mean() > best_avg:
            best_avg, best_x = g.mean(), x
    print(f"  -> X = {best_x}")

    test = tr[tr['event_date'] >= '2024-01-01'].copy()
    test = test[test['ret_chosen'].notna()]
    g = test[test['conf'] >= best_x]
    print("\n" + "=" * 60)
    print(f"FROZEN TEST 2024-2026 | policy {choice} | X={best_x}")
    print("=" * 60)
    u = test['ret_chosen']
    print(f"ungated: n={len(u):5d} win={(u > 0).mean()*100:5.1f}% avg={u.mean():+6.2f}% med={u.median():+6.2f}%")
    print(f"gated  : n={len(g):5d} win={(g['ret_chosen'] > 0).mean()*100:5.1f}% "
          f"avg={g['ret_chosen'].mean():+6.2f}% med={g['ret_chosen'].median():+6.2f}%")
    for y, gy in g.groupby(g['event_date'].dt.year):
        r = gy['ret_chosen']
        print(f"  {y}: n={len(r):4d} win={(r > 0).mean()*100:5.1f}% avg={r.mean():+6.2f}%")

    gg = g.sort_values(['event_date', 'conf'], ascending=[True, False])
    open_until, pnl, taken = [], 0.0, 0
    for _, row in gg.iterrows():
        d0 = row['event_date']
        open_until = [ou for ou in open_until if ou > d0]
        if len(open_until) >= 20:
            continue
        open_until.append(d0 + pd.tseries.offsets.BDay(int(row['days_chosen'])))
        pnl += 5000 * row['ret_chosen'] / 100
        taken += 1
    print(f"\nportfolio sim: {taken} trades, P&L ${pnl:+,.0f} = {pnl/1000:.1f}% on $100k over 2.6y")


if __name__ == '__main__':
    tr = build()
    study(tr)
