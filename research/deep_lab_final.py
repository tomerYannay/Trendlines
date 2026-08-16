"""
FINAL SYNTHESIS + FROZEN TEST for the deep research.

The entry gate is the UNION of the exact confirmed, regime-stable recipes
(verified: exact reproduction, positive in BOTH DEV halves, survives removal
of the best ticker). No new thresholds are invented here.

  U1 upper 'old-steep-line + strong stock':
      ma200_gap>10 & days_since_anchor>150 & slope<-15 & attempt<=4  (+12.91 DEV, h2 +9.03)
      + entry-extension cap gap_vs_line<=3 (the confirmed disaster predictor)
  N1 under 'early touch on very old support':  touch<=5 & dsa>750            (+10.49, h2 +4.03)
  N2 under 'tight geometry':  2<=touch<=8 & 2<=slope<=14 & dsa>=128          (+9.81,  h2 +3.83)
  N3 under 'small-cap shallow line, high ATR': touch<=10 & slope<13.4 & dsa>128
      & dollar_vol<21 & atr>4                                                (+9.06,  h2 +4.26)

Exit: line - 1xATR trailing stop, hold to 90 trading days; upper-only stall-cut
at checkpoint 60 when ret<=0 (verified never to hurt).

Stage 3: the gate is applied ONCE to the locked TEST file (2024-2026).
"""
import json
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd


def gate(df):
    upper = (
        (df.side == 'upper')
        & (df.ma200_gap_pct > 10) & (df.days_since_anchor > 150)
        & (df.slope_yr_pct < -15) & (df.attempt_or_touch <= 4)
        & (df.gap_vs_line_pct <= 3)
    )
    n1 = (df.side == 'under') & (df.attempt_or_touch <= 5) & (df.days_since_anchor > 750)
    n2 = ((df.side == 'under') & (df.attempt_or_touch.between(2, 8))
          & (df.slope_yr_pct.between(2, 14)) & (df.days_since_anchor >= 128))
    n3 = ((df.side == 'under') & (df.attempt_or_touch <= 10) & (df.slope_yr_pct < 13.4)
          & (df.days_since_anchor > 128) & (df.dollar_vol_m < 21) & (df.atr_pct > 4))
    df = df.copy()
    df['rule'] = np.select([upper, n1, n2, n3], ['U1', 'N1', 'N2', 'N3'], default='')
    return df[df['rule'] != '']


def outcome(df):
    """Final trade return: hold-to-90 with the s10 line stop; upper stall-cut at cp60<=0."""
    ret = df['s10_ret_cp90'].copy()
    stall = (df.side == 'upper') & df['s10_ret_cp60'].notna() & (df['s10_ret_cp60'] <= 0) \
            & (df['s10_stop_day'].isna() | (df['s10_stop_day'] > 60))
    ret[stall] = df.loc[stall, 's10_ret_cp60']
    return ret


def report(df, label):
    r = outcome(df).dropna()
    if len(r) == 0:
        print(f"{label}: no trades")
        return
    print(f"{label}: n={len(r):5d} ({df['ticker'].nunique()} tickers)  win={(r > 0).mean()*100:5.1f}%  "
          f"avg={r.mean():+6.2f}%  med={r.median():+6.2f}%")


def main():
    dev = pd.read_csv('research/output/deep_lab_dev.csv', parse_dates=['event_date'])
    g_dev = gate(dev)
    print("=" * 68)
    print("DEV sanity (2020-2023) — the union gate on the discovery set")
    print("=" * 68)
    report(g_dev, 'DEV all  ')
    mid = dev['event_date'].median()
    report(g_dev[g_dev['event_date'] < mid], 'DEV h1   ')
    report(g_dev[g_dev['event_date'] >= mid], 'DEV h2   ')
    for rule, gr in g_dev.groupby('rule'):
        report(gr, f'  {rule}     ')

    print("\n" + "=" * 68)
    print("STAGE 3 — FROZEN TEST 2024-2026 (first and only look)")
    print("=" * 68)
    test = pd.read_csv('research/output/deep_lab_test.csv', parse_dates=['event_date'])
    base = test['s10_ret_cp90'].dropna()
    print(f"baseline (all TEST trades, no gate): n={len(base)}  win={(base > 0).mean()*100:.1f}%  avg={base.mean():+.2f}%")
    g_test = gate(test)
    report(g_test, 'GATED    ')
    for y, gy in g_test.groupby(g_test['event_date'].dt.year):
        report(gy, f'  {y}   ')
    for rule, gr in g_test.groupby('rule'):
        report(gr, f'  {rule}     ')

    # capacity portfolio: $5k/trade, max 20 concurrent
    g = g_test.copy()
    g['ret_final'] = outcome(g)
    g = g[g['ret_final'].notna()].sort_values('event_date')
    g['days_final'] = np.where(g['s10_stop_day'].notna(), g['s10_stop_day'], 90)
    open_until, pnl, taken = [], 0.0, 0
    for _, row in g.iterrows():
        d0 = row['event_date']
        open_until = [u for u in open_until if u > d0]
        if len(open_until) >= 20:
            continue
        open_until.append(d0 + pd.tseries.offsets.BDay(int(row['days_final'])))
        pnl += 5000 * row['ret_final'] / 100
        taken += 1
    print(f"\nportfolio (max 20 slots, $5k/trade): {taken} trades taken, "
          f"P&L ${pnl:+,.0f} = {pnl/1000:+.1f}% on $100k over 2.6y")

    spec = {
        'stop': 'line - 1x ATR14(entry), trailing along the line',
        'horizon_days': 90,
        'stall_cut': 'upper only: exit at day 60 if ret<=0',
        'rules': {
            'U1': "side=='upper' & ma200_gap_pct>10 & days_since_anchor>150 & slope_yr_pct<-15 & attempt<=4 & gap_vs_line_pct<=3",
            'N1': "side=='under' & touch_no<=5 & days_since_anchor>750",
            'N2': "side=='under' & 2<=touch_no<=8 & 2<=slope_yr_pct<=14 & days_since_anchor>=128",
            'N3': "side=='under' & touch_no<=10 & slope_yr_pct<13.4 & days_since_anchor>128 & dollar_vol_m<21 & atr_pct>4",
        },
    }
    with open('research/output/deep_lab_final_spec.json', 'w') as f:
        json.dump(spec, f, indent=1)
    print("final spec saved -> research/output/deep_lab_final_spec.json")


if __name__ == '__main__':
    main()
