"""
STAGE 2 + 3 — discovery on 2020-2023, frozen test on 2024-2026.

Stage 2 (DEV = trades entered <= 2023-12-31):
  A. pick the best TP policy per side (by avg return, sanity-checked on both DEV halves)
  B. feature diagnostics under the chosen policy
  C. train a WOE-logistic confidence model: fit on 2020-2022, calibrate on 2023
  D. pick the entry threshold X on DEV (grid over calibrated confidence)

Stage 3 (TEST = trades entered >= 2024-01-01):
  apply the FROZEN policy + model + threshold to unseen trades;
  report per-year results, gated vs ungated, and a capacity-constrained
  portfolio simulation ($5k/trade, max 20 concurrent).

Usage:  python -m research.exit_lab_stage2
"""
import json
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
from research.confidence import (make_bins, bin_index, woe_table, fit_logistic,
                                 spy_context)

VARIANTS = ['tp10', 'tp15', 'tp20', 'tp30', 'tp40', 'atr2x', 'atr3x', 'atr4x', 'none']
FEATS = ['attempt_or_touch', 'days_since_anchor', 'slope_yr_pct', 'vol_ratio20', 'atr_pct',
         'runup_20d', 'dist_from_ath_pct', 'dist_hi_52w_pct', 'dist_lo_52w_pct', 'rsi14',
         'dollar_vol_m', 'gap_vs_line_pct', 'spy_ret_20d', 'spy_above_ma200']
WOE_SIDE = {'upper': FEATS, 'under': FEATS}


def load_trades():
    tr = pd.read_csv('research/output/exit_lab_trades.csv')
    tr['event_date'] = pd.to_datetime(tr['event_date'])
    tr['attempt_or_touch'] = tr['attempt_no'].fillna(tr['touch_no'])
    spy = spy_context()
    tr['dkey'] = tr['event_date'].dt.date.astype(str)
    tr = tr.join(spy, on='dkey')
    return tr


def stats(r):
    r = r.dropna()
    if len(r) == 0:
        return None
    return dict(n=len(r), win=round((r > 0).mean() * 100, 1), avg=round(r.mean(), 2), med=round(r.median(), 2))


def pick_policy(dev):
    """Best TP variant per side by avg return, requiring both DEV halves positive-ranked."""
    mid = dev['event_date'].median()
    choice = {}
    print("\n=== A. TP policy selection (DEV only) ===")
    for side in ('upper', 'under'):
        d = dev[dev['side'] == side]
        rows = []
        for v in VARIANTS:
            s_all = stats(d[f'ret_{v}'])
            s_h1 = stats(d[d['event_date'] < mid][f'ret_{v}'])
            s_h2 = stats(d[d['event_date'] >= mid][f'ret_{v}'])
            if s_all:
                rows.append((v, s_all, s_h1['avg'] if s_h1 else None, s_h2['avg'] if s_h2 else None))
        rows.sort(key=lambda x: -x[1]['avg'])
        print(f"\n[{side}]  variant | n | win% | avg% | med% | avg h1 | avg h2")
        for v, s, h1, h2 in rows:
            print(f"  {v:6s} n={s['n']:5d} win={s['win']:5.1f}% avg={s['avg']:+6.2f}% med={s['med']:+6.2f}%"
                  f"  h1={h1:+.2f}% h2={h2:+.2f}%")
        # choose the top variant whose edge holds in both halves (h1,h2 > 0 preferred)
        best = next((v for v, s, h1, h2 in rows if h1 is not None and h2 is not None and h1 > 0 and h2 > 0), rows[0][0])
        choice[side] = best
        print(f"  -> chosen for {side}: {best}")
    return choice


def feature_report(dev, choice):
    print("\n=== B. feature diagnostics under the chosen policy (DEV) ===")
    for side in ('upper', 'under'):
        d = dev[dev['side'] == side].copy()
        col = f"ret_{choice[side]}"
        d = d[d[col].notna()]
        d['y'] = d[col] > 0
        spreads = []
        for f in FEATS:
            x = d[f].astype(float)
            if x.notna().sum() < 500:
                continue
            try:
                q = pd.qcut(x, 5, duplicates='drop')
            except Exception:
                continue
            g = d.groupby(q)['y'].mean()
            spreads.append((f, round((g.max() - g.min()) * 100, 1),
                            str(g.idxmax()), round(g.max() * 100, 1)))
        spreads.sort(key=lambda s: -s[1])
        print(f"[{side}] win-rate spread across quintiles (top 6):")
        for f, sp, bucket, top in spreads[:6]:
            print(f"  {f:20s} spread {sp:5.1f}pp | best bucket {bucket} -> {top:.1f}% win")


def fit_model(dev, choice):
    """WOE scorecard per side: fit 2020-2022, calibrate on 2023."""
    calib_start = pd.Timestamp('2023-01-01')
    model = {}
    print("\n=== C. confidence model (fit 2020-2022, calibrate 2023) ===")
    for side in ('upper', 'under'):
        d = dev[dev['side'] == side].copy()
        col = f"ret_{choice[side]}"
        d = d[d[col].notna()]
        d['y'] = (d[col] > 0).astype(float)
        fit_set = d[d['event_date'] < calib_start]
        cal_set = d[d['event_date'] >= calib_start]

        base = fit_set['y'].mean()
        feats, X_cols = {}, []
        for f in WOE_SIDE[side]:
            x = fit_set[f].astype(float).values
            edges = make_bins(x)
            idx = bin_index(x, edges)
            woe = woe_table(idx, fit_set['y'].values, len(edges) + 1, base)
            feats[f] = {'edges': [float(e) for e in edges], 'woe': woe}
            X_cols.append(np.where(idx < 0, 0.0, np.array(woe)[np.clip(idx, 0, len(woe) - 1)]))
        w = fit_logistic(np.column_stack(X_cols), fit_set['y'].values)
        m = {'features': feats, 'w': [float(x) for x in w], 'base_rate': float(base)}

        def raw_p(frame):
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
        cal_curve = []
        for i in range(10):
            msk = (p_cal >= qs[i]) & (p_cal < qs[i + 1] if i < 9 else p_cal <= qs[i + 1])
            if msk.sum():
                cal_curve.append((float(p_cal[msk].mean()), float(cal_set['y'].values[msk].mean()),
                                  int(msk.sum()), float(cal_set[col].values[msk].mean())))
        m['calibration'] = cal_curve
        model[side] = m
        print(f"[{side}] fit n={len(fit_set)}, calib n={len(cal_set)}; calibration (pred -> real | avg ret):")
        for pr, ac, nn, rr in cal_curve:
            print(f"   {pr*100:5.1f}% -> {ac*100:5.1f}%  n={nn:4d}  avg {rr:+5.2f}%")
    return model


def score(frame, m):
    cols = []
    for f, spec in m['features'].items():
        x = frame[f].astype(float).values
        idx = bin_index(x, spec['edges'])
        woe = np.array(spec['woe'])
        cols.append(np.where(idx < 0, 0.0, woe[np.clip(idx, 0, len(woe) - 1)]))
    X = np.column_stack(cols)
    w = np.array(m['w'])
    p_raw = 1 / (1 + np.exp(-(w[0] + X @ w[1:])))
    cal = m['calibration']
    xs = np.array([c[0] for c in cal]); ys = np.array([c[1] for c in cal])
    return np.interp(p_raw, xs, ys) * 100


def pick_threshold(dev, model, choice):
    print("\n=== D. threshold X selection (DEV, gated expectancy) ===")
    best_x, best_avg = None, -1e9
    for side in ('upper', 'under'):
        dev.loc[dev['side'] == side, 'conf'] = score(dev[dev['side'] == side], model[side])
    dev['ret_chosen'] = np.where(dev['side'] == 'upper',
                                 dev[f"ret_{choice['upper']}"], dev[f"ret_{choice['under']}"])
    # percentile-based grid adapted to the model's own confidence distribution
    grid = [round(np.percentile(dev['conf'].dropna(), p), 1) for p in (50, 60, 70, 80, 90)]
    for x in sorted(set(grid)):
        g = dev[dev['conf'] >= x]['ret_chosen'].dropna()
        if len(g) < 300:
            print(f"  X={x}: n={len(g)} (<300, skip)")
            continue
        print(f"  X={x}: n={len(g):5d}  win={(g > 0).mean()*100:5.1f}%  avg={g.mean():+6.2f}%")
        if g.mean() > best_avg:
            best_avg, best_x = g.mean(), x
    print(f"  -> chosen X = {best_x} (avg {best_avg:+.2f}% on DEV)")
    return best_x


def stage3(tr, model, choice, X):
    test = tr[tr['event_date'] >= '2024-01-01'].copy()
    for side in ('upper', 'under'):
        test.loc[test['side'] == side, 'conf'] = score(test[test['side'] == side], model[side])
    test['ret_chosen'] = np.where(test['side'] == 'upper',
                                  test[f"ret_{choice['upper']}"], test[f"ret_{choice['under']}"])
    test['days_chosen'] = np.where(test['side'] == 'upper',
                                   test[f"days_{choice['upper']}"], test[f"days_{choice['under']}"])
    test = test[test['ret_chosen'].notna()]

    print("\n" + "=" * 66)
    print(f"STAGE 3 — FROZEN TEST 2024-2026  (policy {choice}, X={X})")
    print("=" * 66)
    ung = test['ret_chosen']
    g = test[test['conf'] >= X]
    print(f"ungated : n={len(ung):5d}  win={(ung > 0).mean()*100:5.1f}%  avg={ung.mean():+6.2f}%  med={ung.median():+6.2f}%")
    print(f"gated   : n={len(g):5d}  win={(g['ret_chosen'] > 0).mean()*100:5.1f}%  "
          f"avg={g['ret_chosen'].mean():+6.2f}%  med={g['ret_chosen'].median():+6.2f}%")

    print("\nper-year (gated):")
    for y, gy in g.groupby(g['event_date'].dt.year):
        r = gy['ret_chosen']
        print(f"  {y}: n={len(r):4d}  win={(r > 0).mean()*100:5.1f}%  avg={r.mean():+6.2f}%")

    # capacity-constrained portfolio: $5k per trade, max 20 concurrent, conf-ranked
    g = g.sort_values(['event_date', 'conf'], ascending=[True, False])
    open_until = []
    cash_pnl, taken = 0.0, 0
    for _, row in g.iterrows():
        d0 = row['event_date']
        open_until = [u for u in open_until if u > d0]
        if len(open_until) >= 20:
            continue
        open_until.append(d0 + pd.tseries.offsets.BDay(int(row['days_chosen'])))
        cash_pnl += 5000 * row['ret_chosen'] / 100
        taken += 1
    print(f"\nportfolio sim (max 20 slots, $5k/trade): {taken} trades taken, "
          f"P&L ${cash_pnl:+,.0f} on $100k base = {cash_pnl/1000:.1f}% over the period")

    with open('research/output/exit_lab_model.json', 'w') as f:
        json.dump({'model': model, 'policy': choice, 'threshold': X}, f, indent=1)
    print("frozen artifacts saved -> research/output/exit_lab_model.json")


def main():
    tr = load_trades()
    dev = tr[tr['period'] == 'DEV'].copy()
    print(f"trades: {len(tr)} total | DEV {len(dev)} | TEST {len(tr) - len(dev)}")
    choice = pick_policy(dev)
    feature_report(dev, choice)
    model = fit_model(dev, choice)
    X = pick_threshold(dev, model, choice)
    stage3(tr, model, choice, X)


if __name__ == '__main__':
    main()
