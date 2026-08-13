"""
Out-of-sample validation of the confirmed diagonal scenarios.

The scenarios below were DISCOVERED on the 2025-07 -> 2026-08 window.
This script applies their FROZEN filters, unchanged, to event datasets from
earlier windows (2022/2023/2024 anchors) and reports per-period stats —
the honest test of whether the edges are real or curve-fit.

Usage (after building the datasets with research.build_event_dataset):
    python -m research.validate_scenarios_oos
"""
import glob
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db

DATASETS = {
    '2022-23': 'research/output/event_dataset_2022-07-01_2023-07-01.csv',
    '2023-24': 'research/output/event_dataset_2023-07-01_2024-07-01.csv',
    '2024-25': 'research/output/event_dataset_2024-07-01_2025-07-01.csv',
    '2025-26': 'research/output/event_dataset_2025-07-01.csv',   # discovery window
}

WINDOWS = {
    '2022-23': ('2022-07-01', '2023-07-01'),
    '2023-24': ('2023-07-01', '2024-07-01'),
    '2024-25': ('2024-07-01', '2025-07-01'),
    '2025-26': ('2025-07-01', '2026-08-12'),
}


def add_spacing(df):
    """Calendar days since the previous attempt on the same line (upper side)."""
    up = df[df['side'] == 'upper_breakout'].sort_values(['ticker', 'event_date']).copy()
    up['event_date'] = pd.to_datetime(up['event_date'])
    prev = up.groupby('ticker')[['event_date', 'attempt_no', 'days_since_anchor']].shift(1)
    same_line = (up['attempt_no'] == prev['attempt_no'] + 1) & (up['days_since_anchor'] > prev['days_since_anchor'])
    spacing = (up['event_date'] - prev['event_date']).dt.days.where(same_line)
    df.loc[up.index, 'spacing_days'] = spacing
    return df


# frozen filters exactly as confirmed on the discovery window
def SCENARIOS():
    U = lambda d: d[d['side'] == 'upper_breakout']
    S = lambda d: d[(d['side'] == 'under_touch') & (d['close'] >= 5) & (d['slope_yr_pct'] <= 100)]
    return [
        ('UNDER קפיטולציה',            lambda d: S(d)[(S(d)['closed_above']) & (S(d)['runup_20d'] <= -18) & (S(d)['atr_pct'] >= 3.7)]),
        ('UNDER תמיכה בוגרת ושטוחה',   lambda d: S(d)[(S(d)['closed_above']) & (S(d)['days_since_anchor'] >= 100) & (S(d)['slope_yr_pct'] <= 30)]),
        ('UNDER כל נגיעה dv1-10 atr3',  lambda d: S(d)[(S(d)['dollar_vol_m'].between(1, 10)) & (S(d)['atr_pct'] >= 3)]),
        ('UNDER תמיכה בוגרת 50+',       lambda d: S(d)[(S(d)['closed_above']) & (S(d)['days_since_anchor'] >= 50)]),
        ('UPPER ניסיון1 + ווליום x2',   lambda d: U(d)[(U(d)['attempt_no'] == 1) & (U(d)['vol_ratio20'] >= 2) & (U(d)['close'] >= 5)]),
        ('UPPER ניסיון 2+',             lambda d: U(d)[U(d)['attempt_no'] >= 2]),
        ('UPPER ניסיון 2+ נזיל 5-100',  lambda d: U(d)[(U(d)['attempt_no'] >= 2) & (U(d)['close'].between(5, 100)) & (U(d)['dollar_vol_m'] > 10)]),
        ('UPPER מרווח 31-90 יום',       lambda d: U(d)[(U(d)['spacing_days'] > 30) & (U(d)['spacing_days'] <= 90) & (U(d)['close'] >= 5)]),
        ('UPPER ניסיון 1 (בסיס-אזהרה)', lambda d: U(d)[U(d)['attempt_no'] == 1]),
        ('UPPER ניסיון1 ווליום<0.8 (וטו)', lambda d: U(d)[(U(d)['attempt_no'] == 1) & (U(d)['vol_ratio20'] < 0.8)]),
    ]


def spy_avg20(start, end):
    rows = db.fetch_query("""
        SELECT close FROM stock_prices WHERE ticker='SPY' AND date >= %s AND date < %s ORDER BY date;
    """, (start, end))
    s = pd.Series([float(r[0]) for r in rows])
    if len(s) < 25:
        return None
    r20 = (s.shift(-20) / s - 1).dropna() * 100
    return round(r20.mean(), 2)


def main():
    data = {}
    for period, path in DATASETS.items():
        try:
            df = pd.read_csv(path)
        except FileNotFoundError:
            print(f"missing dataset for {period}: {path}")
            continue
        if df['closed_above'].dtype == object:
            df['closed_above'] = df['closed_above'] == True
        df = add_spacing(df)
        data[period] = df

    periods = list(data.keys())
    print("Out-of-sample validation — frozen filters from the 2025-26 discovery window")
    print("cells: avg ret_20d %  (win% | n)\n")

    header = f"{'scenario':38s}" + "".join(f"{p:>22s}" for p in periods)
    print(header)
    print("-" * len(header))

    bench = {p: spy_avg20(*WINDOWS[p]) for p in periods}

    for name, fn in SCENARIOS():
        row = f"{name:38s}"
        for p in periods:
            sub = fn(data[p])
            r = sub['ret_20d'].dropna()
            if len(r) < 30:
                row += f"{'n<30':>22s}"
            else:
                row += f"{r.mean():+7.2f} ({(r > 0).mean() * 100:4.1f}%|{len(r):5d})"
        print(row)

    row = f"{'SPY avg 20d (benchmark)':38s}"
    for p in periods:
        row += f"{bench[p]:+7.2f}{'':15s}" if bench[p] is not None else f"{'n/a':>22s}"
    print(row)

    print("\nper-period event totals:")
    for p in periods:
        d = data[p]
        print(f"  {p}: {len(d)} events ({(d['side'] == 'upper_breakout').sum()} upper / {(d['side'] == 'under_touch').sum()} under)")


if __name__ == '__main__':
    main()
