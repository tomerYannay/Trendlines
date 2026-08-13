"""
Head-to-head comparison of upper-diagonal renewal rule sets.

Runs the walk-forward once per ticker and simulates THREE independent
line-management state machines in parallel on the same prices:

  original    : seq>50,  distance>20%,  ANY close below after breakout re-anchors
  research    : seq>200, distance>100%, only a close >5% below re-anchors
  recommended : seq>60,  distance>25%,  close >5% below re-anchors, PLUS an
                event trigger — a new swing high above the line followed by a
                lower high (>=5 days later) re-anchors immediately, so a fresh
                breakout target exists as soon as structure allows.

Usage:
    python -m research.compare_renewal_rules --as-of 2022-07-01 --until 2023-07-01
"""
import argparse
import os
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import trendline_core as core
from research.build_event_dataset import load

RULESETS = {
    'original_50/20/instant': dict(seq=50, ext=20.0, fail=None, event=False),
    'research_200/100/5': dict(seq=200, ext=100.0, fail=5.0, event=False),
    'recommended_60/25/5+peak': dict(seq=60, ext=25.0, fail=5.0, event=True),
}
PEAK_CONFIRM_DAYS = 5
MIN_PRICE = 2.0


def walk(h, c, hist_n, until_n, rs):
    res0 = core.best_upper_trendline(h[:hist_n])
    if res0 is None:
        return [], 0
    i2, p2, slope = res0[1], h[res0[1]], res0[2]
    seq, prev_bt, attempt, re_n = 0, False, 0, 0
    peak_hi, peak_day = None, None
    events = []
    n = len(c)

    for t in range(hist_n, until_n):
        line_t = float(np.exp(np.log(p2) + slope * (t - i2)))
        bt = c[t] > line_t
        dist = (line_t - c[t]) / c[t] * 100
        s = seq + 1 if bt else 0

        if bt and seq == 0 and c[t] >= MIN_PRICE:
            attempt += 1
            ret20 = (c[t + 20] / c[t] - 1) * 100 if t + 20 < n else None
            events.append((attempt, ret20))

        # event trigger bookkeeping: track the highest high made ABOVE the line
        if rs['event'] and h[t] > line_t and (peak_hi is None or h[t] >= peak_hi):
            peak_hi, peak_day = h[t], t

        failed = (dist > 0 and prev_bt) if rs['fail'] is None else (dist > rs['fail'] and prev_bt)
        flag = (s > rs['seq']) or failed or (dist < -rs['ext'])
        if (rs['event'] and peak_hi is not None
                and t - peak_day >= PEAK_CONFIRM_DAYS and h[t] < peak_hi):
            flag = True   # new swing high above the line has a confirmed lower high after it

        seq, prev_bt = s, bt
        if flag:
            r = core.best_upper_trendline(h[:t + 1])
            if r is not None:
                i2, p2, slope = r[1], h[r[1]], r[2]
                seq, prev_bt, attempt = 0, False, 0
                peak_hi, peak_day = None, None
                re_n += 1

    return events, re_n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-of', required=True)
    ap.add_argument('--until', default=None)
    args = ap.parse_args()
    as_of = pd.Timestamp(args.as_of)
    until = pd.Timestamp(args.until) if args.until else None

    db.cursor.execute("SELECT ticker FROM tickers_russell ORDER BY ticker;")
    tickers = [r[0] for r in db.cursor.fetchall()]

    stats = {name: {'events': [], 're': 0} for name in RULESETS}
    for i, t in enumerate(tickers, 1):
        df = load(t)
        if df is None or len(df) < 80:
            continue
        dates = df['date'].tolist()
        n = len(df)
        hist_n = sum(1 for d in dates if pd.Timestamp(d) < as_of)
        until_n = n if until is None else sum(1 for d in dates if pd.Timestamp(d) < until)
        if hist_n < 80 or until_n <= hist_n:
            continue
        h, c = df['high'].values, df['close'].values
        for name, rs in RULESETS.items():
            evs, re_n = walk(h, c, hist_n, until_n, rs)
            stats[name]['events'].extend(evs)
            stats[name]['re'] += re_n
        if i % 400 == 0:
            print(f"...{i}/{len(tickers)}")

    rows = []
    for name, st in stats.items():
        ev = pd.DataFrame(st['events'], columns=['attempt', 'ret20'])
        valid = ev['ret20'].dropna()
        re2 = ev[ev['attempt'] >= 2]['ret20'].dropna()
        rows.append({
            'ruleset': name, 'as_of': str(as_of.date()),
            'events': len(ev), 'reanchors': st['re'],
            'avg20_all': round(valid.mean(), 2) if len(valid) else None,
            'win20_all': round((valid > 0).mean() * 100, 1) if len(valid) else None,
            'n_att2plus': len(re2),
            'avg20_att2plus': round(re2.mean(), 2) if len(re2) else None,
            'win20_att2plus': round((re2 > 0).mean() * 100, 1) if len(re2) else None,
        })
    out = pd.DataFrame(rows)
    os.makedirs('research/output', exist_ok=True)
    path = f"research/output/renewal_compare_{as_of.date()}.csv"
    out.to_csv(path, index=False)
    print(out.to_string(index=False))
    print(f"saved: {path}")


if __name__ == '__main__':
    main()
