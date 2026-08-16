"""
Confidence engine for diagonal signals.

A transparent WOE-scorecard + logistic model (pure numpy, no sklearn) that
learns from every historical breakout/bounce event (2022-2026, ~62k events)
and outputs, for any new event, a CALIBRATED probability that the stock's
close will be higher in 20 trading days — plus the per-feature contribution
breakdown, so every score is explainable.

Two separate models (the research showed different dynamics):
  * upper : breakout events above the resistance diagonal
  * under : touch/bounce events on the support diagonal

Commands (run from the project root):
    python -m research.confidence train      # (re)train from all event datasets, temporal validation report
    python -m research.confidence predict    # detect today's events, score them, store in signal_predictions
    python -m research.confidence evaluate   # fill realized outcomes for old predictions, calibration report

The learning loop: predict daily -> evaluate weekly -> retrain monthly
(train automatically includes any newer event datasets you build).
"""
import argparse
import glob
import json
import os
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db

MODEL_PATH = 'research/output/confidence_model.json'
MODEL_OOS_PATH = 'research/output/confidence_model_oos.json'
N_BINS = 5
L2 = 2.0
WOE_SMOOTH = 20          # pseudo-events per bin against overconfident small bins
CALIB_MONTHS = 6         # temporal calibration slice taken from the END of the usable data
OUTCOME_LAG_DAYS = 45    # calendar days until a 20-trading-day outcome is fully known

FEATURES = {
    'upper': ['attempt_no', 'days_since_anchor', 'slope_yr_pct', 'vol_ratio20', 'atr_pct',
              'runup_20d', 'dist_from_ath_pct', 'dollar_vol_m', 'gap_vs_line_pct',
              'spy_ret_20d', 'spy_above_ma200'],
    'under': ['touch_no', 'days_since_anchor', 'slope_yr_pct', 'vol_ratio20', 'atr_pct',
              'runup_20d', 'dist_from_ath_pct', 'dollar_vol_m', 'pierce_depth_pct',
              'closed_above', 'spy_ret_20d', 'spy_above_ma200'],
}

FEATURE_LABELS_HE = {
    'attempt_no': 'מספר ניסיון פריצה', 'touch_no': 'מספר נגיעה בתמיכה',
    'days_since_anchor': 'בגרות הקו', 'slope_yr_pct': 'שיפוע הקו',
    'vol_ratio20': 'ווליום יחסי', 'atr_pct': 'תנודתיות (ATR)',
    'runup_20d': 'ראן-אפ 20 יום', 'dist_from_ath_pct': 'מרחק מהשיא',
    'dollar_vol_m': 'מחזור דולרי', 'gap_vs_line_pct': 'פער מהקו',
    'pierce_depth_pct': 'עומק חדירה', 'closed_above': 'סגירה מעל הקו',
    'spy_ret_20d': 'מגמת השוק (SPY 20י)', 'spy_above_ma200': 'משטר שוק (SPY>MA200)',
}


# ---------------------------------------------------------------- market context

def spy_context():
    """date -> (trailing 20d SPY return %, above MA200 flag)."""
    rows = db.fetch_query("SELECT date, close FROM stock_prices WHERE ticker='SPY' ORDER BY date;")
    df = pd.DataFrame(rows, columns=['date', 'close'])
    df['close'] = df['close'].astype(float)
    df['spy_ret_20d'] = (df['close'] / df['close'].shift(20) - 1) * 100
    df['spy_above_ma200'] = (df['close'] > df['close'].rolling(200).mean()).astype(float)
    df['date'] = df['date'].astype(str)
    return df.set_index('date')[['spy_ret_20d', 'spy_above_ma200']]


def add_market_context(ev, spy):
    ev = ev.copy()
    ev['event_date'] = ev['event_date'].astype(str)
    ev = ev.join(spy, on='event_date')
    return ev


# ---------------------------------------------------------------- scorecard math

def make_bins(x, n=N_BINS):
    qs = np.nanquantile(x, np.linspace(0, 1, n + 1)[1:-1])
    return sorted(set(np.round(qs, 6)))


def bin_index(x, edges):
    """np.digitize with NaN -> -1 (neutral bin)."""
    idx = np.digitize(x, edges)
    idx = np.where(np.isnan(x), -1, idx)
    return idx.astype(int)


def woe_table(idx, y, n_bins, base_rate):
    """Weight-of-evidence per bin, Laplace-smoothed toward the base rate."""
    woes = []
    for b in range(n_bins):
        m = idx == b
        wins = y[m].sum() + WOE_SMOOTH * base_rate
        total = m.sum() + WOE_SMOOTH
        p = wins / total
        woes.append(float(np.log(p / (1 - p)) - np.log(base_rate / (1 - base_rate))))
    return woes


def fit_logistic(X, y, l2=L2, iters=60):
    """Newton/IRLS logistic regression with L2 (intercept unpenalized)."""
    X1 = np.hstack([np.ones((len(X), 1)), X])
    w = np.zeros(X1.shape[1])
    pen = np.r_[0.0, np.ones(X1.shape[1] - 1)] * l2
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X1 @ w))
        g = X1.T @ (y - p) - pen * w
        H = -(X1.T * (p * (1 - p))) @ X1 - np.diag(pen + 1e-9)
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def transform(ev, model_side):
    """events df -> WOE feature matrix using a trained side-model dict."""
    cols = []
    for feat, spec in model_side['features'].items():
        x = ev[feat].astype(float).values if feat in ev.columns else np.full(len(ev), np.nan)
        idx = bin_index(x, spec['edges'])
        woe = np.array(spec['woe'])
        col = np.where(idx < 0, 0.0, woe[np.clip(idx, 0, len(woe) - 1)])
        cols.append(col)
    return np.column_stack(cols)


def raw_score(ev, model_side):
    X = transform(ev, model_side)
    w = np.array(model_side['w'])
    z = w[0] + X @ w[1:]
    return 1 / (1 + np.exp(-z)), X


def calibrated(p_raw, model_side):
    """Map raw model probability through the held-out calibration curve."""
    cal = model_side.get('calibration')
    if not cal:
        return p_raw
    xs = np.array([c[0] for c in cal])
    ys = np.array([c[1] for c in cal])
    return np.interp(p_raw, xs, ys)


def contributions(ev_row_X, model_side):
    """Per-feature score contribution (log-odds points) for one event."""
    w = np.array(model_side['w'])[1:]
    names = list(model_side['features'].keys())
    contr = ev_row_X * w
    order = np.argsort(-np.abs(contr))
    return [(names[i], round(float(contr[i]), 3)) for i in order]


# ---------------------------------------------------------------- training

def load_all_events():
    frames = []
    for path in sorted(glob.glob('research/output/event_dataset_*.csv')):
        f = pd.read_csv(path)
        f['dataset'] = os.path.basename(path)
        frames.append(f)
    ev = pd.concat(frames, ignore_index=True)
    # one row per (ticker, side, event_date) in case dataset windows ever overlap
    ev = ev.drop_duplicates(subset=['ticker', 'side', 'event_date'])
    if ev['closed_above'].dtype == object:
        ev['closed_above'] = (ev['closed_above'] == True).astype(float)
    return ev


def side_frame(ev, side):
    key = 'upper_breakout' if side == 'upper' else 'under_touch'
    d = ev[(ev['side'] == key) & ev['ret_20d'].notna() & (ev['close'] >= 2)].copy()
    d['y'] = (d['ret_20d'] > 0).astype(float)
    return d


def fit_side(train, side):
    y = train['y'].values
    base = y.mean()
    feats = {}
    X_cols = []
    for feat in FEATURES[side]:
        x = train[feat].astype(float).values if feat in train.columns else np.full(len(train), np.nan)
        edges = make_bins(x)
        idx = bin_index(x, edges)
        woe = woe_table(idx, y, len(edges) + 1, base)
        feats[feat] = {'edges': [float(e) for e in edges], 'woe': woe}
        X_cols.append(np.where(idx < 0, 0.0, np.array(woe)[np.clip(idx, 0, len(woe) - 1)]))
    X = np.column_stack(X_cols)
    w = fit_logistic(X, y)
    return {'features': feats, 'w': [float(v) for v in w], 'base_rate': float(base)}


def decile_calibration(p, y, ret):
    out = []
    qs = np.quantile(p, np.linspace(0, 1, 11))
    for i in range(10):
        m = (p >= qs[i]) & (p <= qs[i + 1] if i == 9 else p < qs[i + 1])
        if m.sum() == 0:
            continue
        out.append((float(p[m].mean()), float(y[m].mean()), int(m.sum()), float(ret[m].mean())))
    return out


def calibration_report(p, y, ret, label):
    """Bucket report + Brier + expected calibration error (ECE)."""
    cal = decile_calibration(p, y, ret)
    brier = float(np.mean((p - y) ** 2))
    naive = float(y.mean() * (1 - y.mean()))
    n_tot = sum(c[2] for c in cal)
    ece = sum(c[2] * abs(c[0] - c[1]) for c in cal) / max(1, n_tot)
    print(f"\n--- calibration report: {label} ---")
    print(f"n={len(y)}  base win {y.mean() * 100:.1f}%  Brier {brier:.4f} (naive {naive:.4f})  ECE {ece * 100:.2f}pp")
    print("bucket: predicted -> realized | n | avg ret_20d")
    for pr, act, n, r in cal:
        print(f"  {pr * 100:5.1f}% -> {act * 100:5.1f}%  n={n:5d}  avg {r:+5.2f}%")
    return cal, brier, ece


def cmd_train(oos_cutoff=None):
    """
    Clean temporal training: the model is FIT on events before the calibration
    window, the calibration curve is measured on that window using the SAME
    fitted model (no refit afterwards), and both are frozen together.

    oos_cutoff: if given (e.g. 2025-09-01), only events whose 20d outcome was
    fully known before that date are used at all — producing a frozen model
    with zero look-ahead relative to the cutoff (saved to MODEL_OOS_PATH).
    """
    print("loading event datasets...")
    ev = add_market_context(load_all_events(), spy_context())
    ev['event_date_ts'] = pd.to_datetime(ev['event_date'])

    if oos_cutoff is not None:
        cutoff = pd.Timestamp(oos_cutoff)
        usable_end = cutoff - pd.Timedelta(days=OUTCOME_LAG_DAYS)
        ev = ev[ev['event_date_ts'] <= usable_end]
        out_path = MODEL_OOS_PATH
        mode = f"OOS frozen (no information after {cutoff.date()})"
    else:
        usable_end = ev['event_date_ts'].max() - pd.Timedelta(days=OUTCOME_LAG_DAYS)
        ev = ev[ev['event_date_ts'] <= usable_end]
        out_path = MODEL_PATH
        mode = "live (full history)"

    calib_start = usable_end - pd.DateOffset(months=CALIB_MONTHS)
    print(f"mode: {mode}\nfit: events < {calib_start.date()} | calibrate: {calib_start.date()}..{usable_end.date()}")

    model = {}
    for side in ('upper', 'under'):
        d = side_frame(ev, side)
        fit_set = d[d['event_date_ts'] < calib_start]
        cal_set = d[d['event_date_ts'] >= calib_start]
        print(f"\n=== {side}: fit n={len(fit_set)}, calibration n={len(cal_set)} ===")

        m = fit_side(fit_set, side)                      # fitted ONCE — never refit
        p_cal, _ = raw_score(cal_set, m)
        cal, brier, ece = calibration_report(
            p_cal, cal_set['y'].values, cal_set['ret_20d'].values, f"{side} (temporal calibration slice)")

        m['calibration'] = [(pr, act) for pr, act, _, _ in cal]
        m['calibration_detail'] = [{'predicted': pr, 'realized': act, 'n': n, 'avg_ret_20d': r}
                                   for pr, act, n, r in cal]
        m['brier'] = brier
        m['ece'] = ece
        m['fit_through'] = str(calib_start.date())
        m['calibrated_through'] = str(usable_end.date())
        m['mode'] = mode
        model[side] = m

        names = FEATURES[side]
        weights = m['w'][1:]
        order = np.argsort(-np.abs(weights))
        print("feature weights (|w| desc):")
        for i in order:
            print(f"  {names[i]:20s} {weights[i]:+.3f}")

    os.makedirs('research/output', exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(model, f, indent=1)
    print(f"\nmodel saved: {out_path}")


def expected_ret_20d(conf_pct, model_side):
    """Expected 20d return implied by the calibration bucket the confidence falls in.
    Kept SEPARATE from the probability — confidence is never presented as expected profit."""
    detail = model_side.get('calibration_detail')
    if not detail:
        return None
    xs = np.array([c['realized'] for c in detail]) * 100
    ys = np.array([c['avg_ret_20d'] for c in detail])
    order = np.argsort(xs)
    return float(np.interp(conf_pct, xs[order], ys[order]))


# ---------------------------------------------------------------- serving

def ensure_table():
    db.cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_predictions (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR NOT NULL,
            side VARCHAR NOT NULL,
            event_date DATE NOT NULL,
            confidence NUMERIC NOT NULL,
            event_close NUMERIC,
            features JSONB,
            top_drivers TEXT,
            predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actual_ret_20d NUMERIC,
            evaluated_at TIMESTAMP,
            UNIQUE (ticker, side, event_date)
        );
    """)
    db.connection.commit()


def detect_recent_events(lookback_days=5):
    """Re-run the walk-forward (anchor = 1 year back) and keep the last few days' events."""
    from research.build_event_dataset import analyze
    db.cursor.execute("SELECT MAX(date) FROM stock_prices;")
    last_date = db.cursor.fetchone()[0]
    as_of = pd.Timestamp(last_date) - pd.Timedelta(days=365)
    cutoff = pd.Timestamp(last_date) - pd.Timedelta(days=lookback_days)

    db.cursor.execute("SELECT ticker FROM tickers_russell ORDER BY ticker;")
    tickers = [r[0] for r in db.cursor.fetchall()]
    print(f"scanning {len(tickers)} tickers | lines anchored {as_of.date()} | events since {cutoff.date()}")

    events = []
    for i, t in enumerate(tickers, 1):
        try:
            for e in analyze(t, as_of):
                if pd.Timestamp(e['event_date']) >= cutoff:
                    events.append(e)
        except Exception:
            continue
        if i % 400 == 0:
            print(f"  ...{i}/{len(tickers)}")
    return pd.DataFrame(events)


def cmd_predict(lookback_days=5):
    with open(MODEL_PATH) as f:
        model = json.load(f)
    ensure_table()

    ev = detect_recent_events(lookback_days)
    if ev.empty:
        print("no recent events found")
        return
    if ev['closed_above'].dtype == object:
        ev['closed_above'] = (ev['closed_above'] == True).astype(float)
    ev = add_market_context(ev, spy_context())

    stored = 0
    rows_out = []
    for side, key in (('upper', 'upper_breakout'), ('under', 'under_touch')):
        d = ev[ev['side'] == key].copy()
        if d.empty:
            continue
        p_raw, X = raw_score(d, model[side])
        p_cal = calibrated(p_raw, model[side])
        for j, (_, row) in enumerate(d.iterrows()):
            drivers = contributions(X[j], model[side])[:3]
            drv_txt = ', '.join(f"{FEATURE_LABELS_HE.get(k, k)} {'+' if v > 0 else ''}{v}" for k, v in drivers)
            feat_json = {k: (None if pd.isna(row.get(k)) else float(row.get(k)))
                         for k in FEATURES[side] if k in row.index}
            db.cursor.execute("""
                INSERT INTO signal_predictions (ticker, side, event_date, confidence, event_close, features, top_drivers)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, side, event_date) DO UPDATE
                SET confidence = EXCLUDED.confidence, top_drivers = EXCLUDED.top_drivers;
            """, (row['ticker'], side, row['event_date'], round(float(p_cal[j]) * 100, 1),
                  float(row['close']), json.dumps(feat_json), drv_txt))
            stored += 1
            rows_out.append((row['ticker'], side, str(row['event_date']), round(float(p_cal[j]) * 100, 1),
                             float(row['close']), drv_txt))
    db.connection.commit()

    rows_out.sort(key=lambda r: -r[3])
    print(f"\nstored/updated {stored} predictions in signal_predictions. Top confidence:")
    print(f"{'ticker':7s} {'side':6s} {'date':11s} {'conf':>6s}  {'close':>8s}  drivers")
    for r in rows_out[:20]:
        print(f"{r[0]:7s} {r[1]:6s} {r[2]:11s} {r[3]:5.1f}%  {r[4]:8.2f}  {r[5]}")


def cmd_evaluate():
    ensure_table()
    db.cursor.execute("""
        SELECT id, ticker, event_date FROM signal_predictions
        WHERE actual_ret_20d IS NULL;
    """)
    pending = db.cursor.fetchall()
    filled = 0
    for pid, ticker, event_date in pending:
        db.cursor.execute("""
            SELECT close FROM stock_prices
            WHERE ticker = %s AND date >= %s
            ORDER BY date
            LIMIT 21;
        """, (ticker, event_date))
        closes = [float(r[0]) for r in db.cursor.fetchall()]
        if len(closes) < 21:
            continue   # not enough trading days elapsed yet
        ret = (closes[20] / closes[0] - 1) * 100
        db.cursor.execute("""
            UPDATE signal_predictions
            SET actual_ret_20d = %s, evaluated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (round(ret, 2), pid))
        filled += 1
    db.connection.commit()
    print(f"evaluated {filled} predictions ({len(pending) - filled} still maturing)")

    rows = db.fetch_query("""
        SELECT confidence, actual_ret_20d FROM signal_predictions WHERE actual_ret_20d IS NOT NULL;
    """)
    if not rows:
        return
    d = pd.DataFrame(rows, columns=['conf', 'ret']).astype(float)
    d['hit'] = d['ret'] > 0
    print(f"\nlive calibration so far ({len(d)} matured predictions):")
    for lo, hi in [(0, 45), (45, 55), (55, 65), (65, 100)]:
        m = d[(d['conf'] >= lo) & (d['conf'] < hi)]
        if len(m):
            print(f"  conf {lo:2d}-{hi:3d}%: n={len(m):4d}  realized win {m['hit'].mean() * 100:5.1f}%  avg ret {m['ret'].mean():+5.2f}%")
    brier = float(np.mean((d['conf'] / 100 - d['hit']) ** 2))
    print(f"  Brier score: {brier:.4f} (lower is better)")
    print("\nwhen enough new outcomes accumulate, retrain with: python -m research.confidence train")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('command', choices=['train', 'predict', 'evaluate'])
    ap.add_argument('--lookback-days', type=int, default=5, help='predict: scan events from the last N calendar days')
    ap.add_argument('--oos-cutoff', default=None,
                    help='train: freeze a model using only information available before this date (saved separately)')
    args = ap.parse_args()
    if args.command == 'train':
        cmd_train(args.oos_cutoff)
    elif args.command == 'predict':
        cmd_predict(args.lookback_days)
    else:
        cmd_evaluate()


if __name__ == '__main__':
    main()
