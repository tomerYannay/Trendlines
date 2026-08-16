"""
Automated tests for the dashboard engine, wallet, and confidence plumbing.
Pure-synthetic where possible (no DB writes; DB reads only for model/spy files).

Run:  python -m tests_platform
"""
import warnings

warnings.filterwarnings('ignore')

import json

import numpy as np
import pandas as pd

import dashboard.engine as eng
from dashboard.engine import walk_frame, classify_ticker, simulate_wallet, AS_OF, WALLET_START

RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, 'PASS', ''))
    except AssertionError as e:
        RESULTS.append((name, 'FAIL', str(e)))
    except Exception as e:
        RESULTS.append((name, 'ERROR', f'{type(e).__name__}: {e}'))


# ------------------------------------------------------------------ synthetic frames

def hist_dates():
    return pd.bdate_range(end='2019-12-31', periods=100)


def eval_dates(n):
    return pd.bdate_range(start='2020-01-02', periods=n)


def wallet_dates(n):
    # the wallet only trades from WALLET_START onward
    return pd.bdate_range(start='2025-09-01', periods=n)


def make_frame(closes_eval, highs_eval=None, lows_eval=None,
               hist_high0=100.0, hist_high_last=99.9, hist_base=95.0, under=False):
    """History engineered so the anchored line is ~flat at 100 (upper)
    or ~flat at 10 (under), making crossings predictable."""
    hd = hist_dates()
    n_h = len(hd)
    if not under:
        highs = np.full(n_h, hist_base); highs[0] = hist_high0; highs[-1] = hist_high_last
        lows = highs - 5; closes = highs - 2
    else:
        lows = np.full(n_h, 12.0); lows[0] = 10.0; lows[-1] = 10.01
        highs = lows + 4; closes = lows + 2
    ed = eval_dates(len(closes_eval))
    ce = np.array(closes_eval, dtype=float)
    he = np.array(highs_eval, dtype=float) if highs_eval is not None else ce + 0.5
    le = np.array(lows_eval, dtype=float) if lows_eval is not None else ce - 0.5
    df = pd.DataFrame({
        'date': list(hd.date) + list(ed.date),
        'high': np.r_[highs, he], 'low': np.r_[lows, le],
        'close': np.r_[closes, ce], 'volume': np.full(n_h + len(ce), 1e6),
    })
    return df


# ------------------------------------------------------------------ walk-forward tests

def test_upper_attempt_counting():
    # 98 below → 101 breakout(1) → 99.5 shallow dip (<5% below line ~100) → 101.5 breakout(2)
    df = make_frame([98, 101, 99.5, 101.5, 101.6])
    evs, _ = walk_frame(df, 'TEST')
    ups = [e for e in evs if e['side'] == 'upper_breakout']
    assert [e['attempt_no'] for e in ups] == [1, 2], f"attempts={[e['attempt_no'] for e in ups]}"


def test_under_touch_counting():
    # touch (low<=line, close above) → 3 quiet days (spacing rule) → touch again
    df = make_frame([10.5, 11, 11, 11, 11, 10.6, 11],
                    lows_eval=[9.9, 10.8, 10.8, 10.8, 10.8, 9.95, 10.8], under=True)
    evs, _ = walk_frame(df, 'TEST')
    tus = [e for e in evs if e['side'] == 'under_touch']
    assert [e['touch_no'] for e in tus] == [1, 2], f"touches={[e['touch_no'] for e in tus]}"
    assert all(e['closed_above'] for e in tus)


def test_renewal_on_deep_failure():
    # breakout(1) → close 90 (>5% below the ~100 line) → line re-anchors → next cross is attempt 1 again
    df = make_frame([101, 90, 90, 96, 101, 101.2],
                    highs_eval=[101.5, 91, 91, 96.5, 101.5, 101.6])
    evs, _ = walk_frame(df, 'TEST')
    ups = [e for e in evs if e['side'] == 'upper_breakout']
    assert len(ups) >= 2, f"expected >=2 breakouts, got {len(ups)}"
    assert ups[0]['attempt_no'] == 1
    assert ups[1]['attempt_no'] == 1, f"after deep failure the line must re-anchor (got attempt {ups[1]['attempt_no']})"


def test_renewal_on_gradual_deep_failure():
    # the CMS case: breakout, shallow failure, then a slow drift below -5% —
    # the line must reset even though no single day followed a close-above day
    df = make_frame([101, 99.5, 97, 93, 96, 101, 101.2],
                    highs_eval=[101.5, 100, 97.5, 93.5, 96.5, 101.5, 101.6])
    evs, _ = walk_frame(df, 'TEST')
    ups = [e for e in evs if e['side'] == 'upper_breakout']
    assert len(ups) >= 2, f"expected a post-reset breakout, got {len(ups)}"
    assert ups[0]['attempt_no'] == 1
    assert ups[1]['attempt_no'] == 1, \
        f"gradual deep failure must reset the line (got attempt {ups[1]['attempt_no']})"


def test_classification():
    assert classify_ticker(None, '2026-08-11') == 'NO_DATA'
    small = pd.DataFrame({'date': pd.bdate_range(end='2026-08-11', periods=10).date})
    assert classify_ticker(small, '2026-08-11') == 'INSUFFICIENT_HISTORY'
    old = pd.DataFrame({'date': pd.bdate_range(end='2025-11-20', periods=100).date})
    assert classify_ticker(old, '2026-08-11') == 'DELISTED_OR_SYMBOL_CHANGED'
    stale = pd.DataFrame({'date': pd.bdate_range(end='2026-08-01', periods=100).date})
    assert classify_ticker(stale, '2026-08-11') == 'STALE_DATA'
    ok = pd.DataFrame({'date': pd.bdate_range(end='2026-08-11', periods=100).date})
    assert classify_ticker(ok, '2026-08-11') == 'OK'


# ------------------------------------------------------------------ wallet tests

def sig(ticker, date, conf, close=10.0):
    return {'ticker': ticker, 'side': 'upper_breakout', 'event_date': date, 'close': close,
            'confidence': conf, 'attempt_no': 2, 'days_since_anchor': 100,
            'slope_yr_pct': -5.0, 'closed_above': True}


def flat_px(tickers, days, price=10.0, bars_until=None):
    cal = wallet_dates(days)
    frames = {}
    for tk in tickers:
        cut = bars_until.get(tk, days) if bars_until else days
        f = pd.DataFrame({'date': cal[:cut], 'open': price, 'high': price, 'low': price, 'close': price})
        f['date'] = pd.to_datetime(f['date'])
        frames[tk] = f.set_index('date')
    return (lambda t: frames[t]), [pd.Timestamp(d) for d in cal]


def test_wallet_selects_highest_confidence():
    day = wallet_dates(1)[0].date()
    signals = pd.DataFrame([sig('AAA', day, 55.0), sig('BBB', day, 75.0), sig('CCC', day, 65.0)])
    px, cal = flat_px(['AAA', 'BBB', 'CCC'], 5)
    old = eng.MAX_OPEN
    eng.MAX_OPEN = 1
    try:
        trades, open_pos, _, _ = simulate_wallet(signals, px=px, calendar=cal)
    finally:
        eng.MAX_OPEN = old
    held = set(open_pos['ticker']) | set(trades['ticker'] if len(trades) else [])
    assert held == {'BBB'}, f"expected the 75% signal (BBB), wallet held {held}"


def test_sl_precedence_over_tp():
    day0 = wallet_dates(1)[0].date()
    signals = pd.DataFrame([sig('XXX', day0, 70.0, close=100.0)])
    cal = [pd.Timestamp(d) for d in wallet_dates(3)]
    f = pd.DataFrame({'date': cal,
                      'open': [100, 100, 100], 'high': [100, 125, 100],
                      'low': [100, 85, 100], 'close': [100, 100, 100]}).set_index('date')
    trades, _, _, _ = simulate_wallet(signals, px=lambda t: f, calendar=cal)
    assert len(trades) == 1 and trades.iloc[0]['reason'] == 'SL', f"expected SL exit, got {trades.to_dict('records')}"
    assert trades.iloc[0]['exit'] == 90.0


def test_time_exit_exactly_40():
    day0 = wallet_dates(1)[0].date()
    signals = pd.DataFrame([sig('YYY', day0, 70.0, close=100.0)])
    px, cal = flat_px(['YYY'], 60, price=100.0)
    trades, open_pos, _, _ = simulate_wallet(signals, px=px, calendar=cal)
    assert len(trades) == 1 and trades.iloc[0]['reason'] == 'TIME'
    assert trades.iloc[0]['days_held'] == eng.EXIT_POLICY['time_days'], \
        f"days_held={trades.iloc[0]['days_held']}"


def test_missing_bars_cannot_hold_position_forever():
    # ticker prints bars only on its entry day, then disappears
    day0 = wallet_dates(1)[0].date()
    signals = pd.DataFrame([sig('ZZZ', day0, 70.0, close=100.0)])
    px, cal = flat_px(['ZZZ'], 60, price=100.0, bars_until={'ZZZ': 1})
    trades, open_pos, _, issues = simulate_wallet(signals, px=px, calendar=cal)
    assert len(open_pos) == 0, "stale position must not stay open"
    assert len(trades) == 1 and trades.iloc[0]['reason'] == 'STALE'
    assert trades.iloc[0]['days_held'] <= eng.EXIT_POLICY['time_days']
    assert issues, "stale close must be reported as a data issue"


def test_wallet_deterministic():
    day0 = wallet_dates(1)[0].date()
    signals = pd.DataFrame([sig('AAA', day0, 60.0), sig('BBB', day0, 70.0)])
    px, cal = flat_px(['AAA', 'BBB'], 50)
    r1 = simulate_wallet(signals, px=px, calendar=cal)
    r2 = simulate_wallet(signals, px=px, calendar=cal)
    assert r1[0].equals(r2[0]) and r1[1].equals(r2[1]) and r1[2].equals(r2[2])


# ------------------------------------------------------------------ model / scoring tests

def test_quality_wallet_no_duplicate_ticker():
    # two qualifying events on the SAME ticker while the first is still open -> only one taken
    ev = pd.DataFrame([
        {'ticker': 'DUP', 'q_rule': 'N1', 'event_date': '2026-01-05', 'close': 10.0,
         'q_status': 'CLOSED', 'q_reason': 'TIME', 'q_ret': 5.0, 'q_days': 60, 'q_exit_date': '2026-04-01'},
        {'ticker': 'DUP', 'q_rule': 'N2', 'event_date': '2026-01-20', 'close': 11.0,
         'q_status': 'CLOSED', 'q_reason': 'TIME', 'q_ret': 3.0, 'q_days': 60, 'q_exit_date': '2026-04-15'},
        {'ticker': 'OTH', 'q_rule': 'N1', 'event_date': '2026-01-20', 'close': 9.0,
         'q_status': 'CLOSED', 'q_reason': 'SL', 'q_ret': -4.0, 'q_days': 10, 'q_exit_date': '2026-02-03'},
    ])
    closed, open_pos = eng.build_quality_wallet(ev)
    taken = list(closed['ticker']) + (list(open_pos['ticker']) if len(open_pos) else [])
    assert taken.count('DUP') == 1, f"duplicate ticker entered twice: {taken}"
    assert 'OTH' in taken


def load_model():
    with open(eng.MODEL_OOS_PATH) as f:
        return json.load(f)


def fake_spy():
    dates = [str(d) for d in pd.bdate_range('2025-08-01', '2026-12-31').date]
    return pd.DataFrame({'spy_ret_20d': 1.0, 'spy_above_ma200': 1.0}, index=dates)


def event_row(ticker='EVT', date='2026-08-10'):
    return {'ticker': ticker, 'side': 'upper_breakout', 'event_date': date, 'close': 20.0,
            'line': 19.5, 'gap_vs_line_pct': 2.5, 'slope_yr_pct': -8.0, 'days_since_anchor': 120,
            'vol_ratio20': 1.4, 'atr_pct': 3.0, 'runup_20d': -2.0, 'dist_from_ath_pct': -30.0,
            'dollar_vol_m': 12.0, 'attempt_no': 3}


def test_scoring_deterministic():
    model = load_model()
    ev = pd.DataFrame([event_row(), event_row('EVT2')])
    s1 = eng.score(ev.copy(), model, fake_spy())
    s2 = eng.score(ev.copy(), model, fake_spy())
    assert s1['confidence'].tolist() == s2['confidence'].tolist()
    assert s1['confidence'].notna().all()


def test_approaching_gets_no_event_probability():
    model = load_model()
    states = {'APR': {'ticker': 'APR', 'close': 20.0, 'date': pd.Timestamp('2026-08-11').date(),
                      'upper': {**event_row('APR', '2026-08-11'), 'gap_vs_line_pct': -1.5, 'close': 20.0}}}
    ev = pd.DataFrame([event_row('OTH', '2026-08-10')])
    upper, under, _ = eng.todays_tables(ev, states, model, fake_spy())
    appr = upper[upper['status'] == 'APPROACHING']
    assert len(appr) == 1, f"expected 1 approaching row, got {len(appr)}"
    assert appr['confidence'].isna().all(), "approaching rows must not carry event probability"
    evt = upper[upper['status'] == 'BREAKOUT']
    assert evt['confidence'].notna().all(), "actual events must carry probability"


def test_no_lookahead_in_oos_model():
    # the WALLET must be out-of-sample: model knowledge must end before WALLET_START
    model = load_model()
    for side in ('upper', 'under'):
        assert pd.Timestamp(model[side]['calibrated_through']) < WALLET_START, \
            f"{side}: calibrated_through {model[side]['calibrated_through']} >= WALLET_START {WALLET_START.date()}"
        assert pd.Timestamp(model[side]['fit_through']) < WALLET_START


def main():
    tests = [
        ('upper attempt counting', test_upper_attempt_counting),
        ('under touch counting', test_under_touch_counting),
        ('trendline renewal on deep failure', test_renewal_on_deep_failure),
        ('trendline renewal on GRADUAL deep failure', test_renewal_on_gradual_deep_failure),
        ('data-quality classification', test_classification),
        ('wallet selects highest confidence', test_wallet_selects_highest_confidence),
        ('SL precedence over TP (same candle)', test_sl_precedence_over_tp),
        ('TIME exit at exactly 40 trading days', test_time_exit_exactly_40),
        ('missing bars cannot hold a position', test_missing_bars_cannot_hold_position_forever),
        ('wallet determinism (two runs identical)', test_wallet_deterministic),
        ('quality wallet: no duplicate ticker', test_quality_wallet_no_duplicate_ticker),
        ('confidence scoring deterministic', test_scoring_deterministic),
        ('approaching gets no event probability', test_approaching_gets_no_event_probability),
        ('no look-ahead in OOS model', test_no_lookahead_in_oos_model),
    ]
    for name, fn in tests:
        check(name, fn)
    width = max(len(n) for n, _, _ in RESULTS)
    passed = sum(1 for _, s, _ in RESULTS if s == 'PASS')
    for n, s, msg in RESULTS:
        mark = {'PASS': '✅', 'FAIL': '❌', 'ERROR': '💥'}[s]
        print(f"{mark} {n:{width}s} {s}" + (f"  — {msg}" if msg else ''))
    print(f"\n{passed}/{len(RESULTS)} passed")
    return passed == len(RESULTS)


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
