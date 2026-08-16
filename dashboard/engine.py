"""
Dashboard engine: walk-forward simulation + confidence scoring + paper wallet.

Deterministic by design: every run re-simulates from AS_OF to the latest
trading day in the DB, so the site is always exactly "as of the latest data
day" with no incremental-state drift.

Methodology guarantees:
  * The wallet uses the FROZEN OUT-OF-SAMPLE model (confidence_model_oos.json),
    trained only on information available before AS_OF — no look-ahead.
  * Confidence is shown ONLY for actual events (breakout / support touch).
    APPROACHING candidates get no event probability — the model was not
    trained to answer that question.
  * Position time is counted on the SPY trading calendar, independent of
    whether the individual ticker printed a bar — stale/delisted tickers are
    force-closed and reported, never silently held.
"""
import json
import os
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import trendline_core as core
from research.build_event_dataset import load, precompute, SEQ_DAYS, EXTREME_PCT, FAIL_PCT
from research.confidence import (MODEL_OOS_PATH, FEATURES, FEATURE_LABELS_HE,
                                 spy_context, add_market_context, raw_score, calibrated,
                                 contributions, expected_ret_20d)

AS_OF = pd.Timestamp('2020-01-01')         # diagonals are anchored & walked from here
WALLET_START = pd.Timestamp('2025-09-01')   # wallet trades only where the frozen model is truly out-of-sample

# ---- ENTRY RULES (only edges that survived 4-year out-of-sample validation) ----
CONF_MIN = 55.0            # minimum calibrated confidence %
MIN_PRICE = 5.0
UPPER_MIN_ATTEMPT = 2      # first breakouts are the worst trade — skip them
UNDER_MIN_LINE_AGE = 50    # mature support lines only
UNDER_MAX_SLOPE = 100      # exclude degenerate near-vertical support lines

# ---- WALLET ----
START_CASH = 100_000.0
POSITION_SIZE = 5_000.0
MAX_OPEN = 20

# ---- EXIT POLICY (configurable; only 'fixed_pct' is implemented/enabled).
# Future kinds to compare (NOT enabled): 'atr' (SL/TP in ATR units),
# 'line_invalidation' (exit on close back below the broken line). ----
EXIT_POLICY = {
    'kind': 'fixed_pct',
    'sl_pct': -10.0,       # validated: keeps ~90% of winners, caps the tail
    'tp_pct': +20.0,       # 2:1 reward:risk
    'time_days': 40,       # trading days (SPY calendar), the edge accrues in 20-40d
}
STALE_AFTER_MISSING = 10   # force-close after this many consecutive missing bars

SIMULATION_MODE = 'OUT_OF_SAMPLE'   # frozen model trained before AS_OF; LIVE_FORWARD accrues from deployment

# Universes shown in the dashboard. The WALLET trades the first (russell) only —
# every edge and threshold was validated on that universe; sp500 is watch-only
# and its confidence scores are model transfer, not yet validated there.
UNIVERSES = [
    ('russell', 'tickers_russell', 'ראסל 2000'),
    ('nasdaq', 'tickers_nasdaq', 'נאסד"ק 100'),
    # a ticker in both indexes is displayed under nasdaq only
    ('sp500', '(SELECT ticker FROM tickers_sp500 EXCEPT SELECT ticker FROM tickers_nasdaq) AS sp_ex',
     'S&P 500'),
]
WALLET_UNIVERSE = 'russell'

# ---- QUALITY WALLET (strategy #2) — frozen spec from the deep research
# (research/output/deep_lab_final_spec.json). UNDER side only: the upper rule
# failed its frozen test. Stop = line - 1x ATR trailing; hold up to 90 days.
QUALITY_START = pd.Timestamp('2024-01-01')   # frozen-test start; LIVE_FORWARD accrues from deployment
QUALITY_HORIZON = 90


# ------------------------------------------------------------------ simulation

def walk_frame(df, ticker):
    """Core walk-forward for one ticker's price frame (pure, DB-free, testable).
    Returns (events, state)."""
    dates = df['date'].tolist()
    n = len(df)
    if n < 100:
        return [], None
    hist_n = sum(1 for d in dates if pd.Timestamp(d) < AS_OF)
    hist_n = max(hist_n, 80)          # late IPOs: anchor on their first 80 bars
    if hist_n >= n:
        return [], None

    h, l, c, v = df['high'].values, df['low'].values, df['close'].values, df['volume'].values
    atr14, vol20, ath, runup20 = precompute(df)
    events = []

    def feats(t, side, line_t, slope, i2, extra):
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

    state = {'ticker': ticker, 'close': round(c[-1], 2), 'date': dates[-1]}

    up = core.best_upper_trendline(h[:hist_n])
    if up is not None:
        i1, i2, slope = up[0], up[1], up[2]
        p2 = h[i2]
        seq, attempt, had_breakout = 0, 0, False
        for t in range(hist_n, n):
            line_t = float(np.exp(np.log(p2) + slope * (t - i2)))
            bt = c[t] > line_t
            if bt:
                had_breakout = True
            dist = (line_t - c[t]) / c[t] * 100
            s = seq + 1 if bt else 0
            if bt and seq == 0 and c[t] >= 2.0:
                attempt += 1
                events.append(feats(t, 'upper_breakout', line_t, slope, i2,
                                    {'attempt_no': attempt, 'anchor1': dates[i1], 'anchor2': dates[i2]}))
            # deep failure: after ANY breakout on this line, a close >FAIL_PCT below it
            # (at any later point, not only the day after) resets the diagonal
            flag = (s > SEQ_DAYS) or (had_breakout and dist > FAIL_PCT) or (dist < -EXTREME_PCT)
            seq = s
            if flag:
                r = core.best_upper_trendline(h[:t + 1])
                if r is not None:
                    i1, i2, slope = r[0], r[1], r[2]
                    p2 = h[i2]
                    seq, attempt, had_breakout = 0, 0, False
        t = n - 1
        line_t = float(np.exp(np.log(p2) + slope * (t - i2)))
        state['upper'] = feats(t, 'upper_breakout', line_t, slope, i2,
                               {'attempt_no': attempt + 1, 'anchor1': dates[i1], 'anchor2': dates[i2]})

    un = core.best_under_trendline(l[:hist_n])
    if un is not None:
        j1, j2, slope_u = un[0], un[1], un[2]
        q2 = l[j2]
        seq, prev_bt, touch = 0, False, 0
        last_touch = -10**9
        for t in range(hist_n, n):
            line_t = float(np.exp(np.log(q2) + slope_u * (t - j2)))
            bt = c[t] < line_t
            dist = (line_t - c[t]) / c[t] * 100
            s = seq + 1 if bt else 0
            if l[t] <= line_t and c[t] >= 2.0 and t - last_touch > 3:
                touch += 1
                ev = feats(t, 'under_touch', line_t, slope_u, j2, {
                    'touch_no': touch,
                    'pierce_depth_pct': round((line_t - l[t]) / line_t * 100, 2),
                    'closed_above': bool(c[t] > line_t),
                    'anchor1': dates[j1], 'anchor2': dates[j2],
                })
                ev.update(_quality_eval(t, touch, j2, q2, slope_u, ev, h, l, c, dates))
                events.append(ev)
                last_touch = t
            flag = (s > SEQ_DAYS) or (dist > 0 and prev_bt) or (dist > EXTREME_PCT)
            seq, prev_bt = s, bt
            if flag:
                r = core.best_under_trendline(l[:t + 1])
                if r is not None:
                    j1, j2, slope_u = r[0], r[1], r[2]
                    q2 = l[j2]
                    seq, prev_bt, touch = 0, False, 0
                    last_touch = -10**9
        t = n - 1
        line_t = float(np.exp(np.log(q2) + slope_u * (t - j2)))
        state['under'] = feats(t, 'under_touch', line_t, slope_u, j2, {
            'touch_no': touch + 1, 'pierce_depth_pct': 0.0, 'closed_above': True,
            'anchor1': dates[j1], 'anchor2': dates[j2],
        })

    return events, state


def _quality_eval(t, touch, j2, q2, slope_u, ev, h, l, c, dates):
    """Frozen quality gate (N1/N2/N3) + line-stop outcome for qualifying trades."""
    if not ev['closed_above'] or ev['close'] < MIN_PRICE:
        return {}
    slope_yr = ev['slope_yr_pct']
    dsa = ev['days_since_anchor']
    dv = ev['dollar_vol_m'] or 0
    atr = ev['atr_pct'] or 0
    rule = None
    if touch <= 5 and dsa > 750:
        rule = 'N1'
    elif 2 <= touch <= 8 and 2 <= slope_yr <= 14 and dsa >= 128:
        rule = 'N2'
    elif touch <= 10 and slope_yr < 13.4 and dsa > 128 and dv < 21 and atr > 4:
        rule = 'N3'
    if rule is None:
        return {}
    n = len(c)
    entry = c[t]
    atr_abs = entry * atr / 100 if atr else entry * 0.03
    for u in range(t + 1, min(n, t + 1 + QUALITY_HORIZON)):
        line_u = float(np.exp(np.log(q2) + slope_u * (u - j2)))
        stop_lvl = line_u - atr_abs
        if stop_lvl > 0 and l[u] <= stop_lvl:
            return {'q_rule': rule, 'q_status': 'CLOSED', 'q_reason': 'SL',
                    'q_ret': round((stop_lvl / entry - 1) * 100, 2),
                    'q_days': u - t, 'q_exit_date': dates[u]}
        if u - t == QUALITY_HORIZON:
            return {'q_rule': rule, 'q_status': 'CLOSED', 'q_reason': 'TIME',
                    'q_ret': round((c[u] / entry - 1) * 100, 2),
                    'q_days': QUALITY_HORIZON, 'q_exit_date': dates[u]}
    line_now = float(np.exp(np.log(q2) + slope_u * (n - 1 - j2)))
    return {'q_rule': rule, 'q_status': 'OPEN', 'q_reason': None,
            'q_ret': round((c[-1] / entry - 1) * 100, 2),
            'q_days': n - 1 - t, 'q_exit_date': None,
            'q_stop_today': round(line_now - atr_abs, 2)}


def build_quality_wallet(ev_df):
    """Strategy #2 ledger from gated events: $5k/trade, max 20 concurrent."""
    if 'q_rule' not in ev_df.columns:
        return pd.DataFrame(), pd.DataFrame()
    q = ev_df[ev_df['q_rule'].notna()].copy()
    q['event_date'] = pd.to_datetime(q['event_date'])
    q = q[q['event_date'] >= QUALITY_START].sort_values('event_date')
    open_until, rows = {}, []          # ticker -> exit date: one position per ticker
    for _, r in q.iterrows():
        d0 = r['event_date']
        open_until = {tk: u for tk, u in open_until.items() if u > d0}
        if r['ticker'] in open_until or len(open_until) >= MAX_OPEN:
            continue
        days = int(r['q_days']) if pd.notna(r['q_days']) else QUALITY_HORIZON
        open_until[r['ticker']] = d0 + pd.tseries.offsets.BDay(max(days, 1))
        rows.append({
            'ticker': r['ticker'], 'rule': r['q_rule'], 'entry_date': d0.date(),
            'entry': r['close'], 'status': r['q_status'], 'reason': r['q_reason'],
            'ret_pct': r['q_ret'], 'days': days,
            'exit_date': r['q_exit_date'],
            'stop_today': r.get('q_stop_today'),
            'pnl': round(POSITION_SIZE * (r['q_ret'] or 0) / 100, 2),
        })
    led = pd.DataFrame(rows)
    if led.empty:
        return led, led
    closed = led[led['status'] == 'CLOSED'].copy()
    open_pos = led[led['status'] == 'OPEN'].copy()
    return closed, open_pos


def quality_equity_curve(ledger):
    """Daily $100k-based equity curve for the quality wallet (same reporting
    format as wallet #1). Marks each position daily at its ticker's close."""
    if ledger.empty:
        return pd.DataFrame(columns=['date', 'equity'])
    cal_rows = db.fetch_query(
        "SELECT date FROM stock_prices WHERE ticker='SPY' AND date >= %s ORDER BY date;",
        (QUALITY_START.date(),))
    calendar = [pd.Timestamp(r[0]) for r in cal_rows]
    led = ledger.copy()
    led['entry_date'] = pd.to_datetime(led['entry_date'])
    led['exit_ts'] = pd.to_datetime(led['exit_date'])
    px_cache = {}

    def closes(tk):
        if tk not in px_cache:
            rows = db.fetch_query(
                "SELECT date, close FROM stock_prices WHERE ticker=%s AND date >= %s ORDER BY date;",
                (tk, QUALITY_START.date()))
            f = pd.DataFrame(rows, columns=['date', 'close'])
            f['close'] = f['close'].astype(float)
            f['date'] = pd.to_datetime(f['date'])
            px_cache[tk] = f.set_index('date')['close']
        return px_cache[tk]

    equity = []
    for day in calendar:
        val = START_CASH
        for _, r in led.iterrows():
            if r['entry_date'] > day:
                continue
            if pd.notna(r['exit_ts']) and r['exit_ts'] <= day:
                val += POSITION_SIZE * r['ret_pct'] / 100          # realized
            else:
                s = closes(r['ticker'])
                past = s[s.index <= day]
                last = float(past.iloc[-1]) if len(past) else r['entry']
                val += POSITION_SIZE * (last / r['entry'] - 1)     # open MTM
        equity.append({'date': day.date(), 'equity': round(val, 2)})
    return pd.DataFrame(equity)


def classify_ticker(df, global_last_date):
    """Data-quality classification for the diagnostics summary."""
    if df is None or df.empty:
        return 'NO_DATA'
    if len(df) < 80:
        return 'INSUFFICIENT_HISTORY'
    last = pd.Timestamp(df['date'].iloc[-1])
    gap = (pd.Timestamp(global_last_date) - last).days
    if gap > 30:
        return 'DELISTED_OR_SYMBOL_CHANGED'
    if gap > 7:
        return 'STALE_DATA'
    return 'OK'


def simulate_all(ticker_table='tickers_russell'):
    db.cursor.execute(f"SELECT ticker FROM {ticker_table} ORDER BY ticker;")
    tickers = [r[0] for r in db.cursor.fetchall()]
    db.cursor.execute("SELECT MAX(date) FROM stock_prices;")
    global_last = db.cursor.fetchone()[0]

    all_events, states = [], {}
    diag = {'scanned': 0, 'processed': 0, 'by_reason': {}}
    for i, t in enumerate(tickers, 1):
        diag['scanned'] += 1
        try:
            df = load(t)
            status = classify_ticker(df, global_last)
            if status in ('NO_DATA', 'INSUFFICIENT_HISTORY'):
                diag['by_reason'][status] = diag['by_reason'].get(status, 0) + 1
                continue
            evs, st = walk_frame(df, t)
            all_events.extend(evs)
            if st is not None:
                st['data_status'] = status
                states[t] = st
            diag['processed'] += 1
            if status != 'OK':
                diag['by_reason'][status] = diag['by_reason'].get(status, 0) + 1
        except Exception as e:
            diag['by_reason']['UNKNOWN_ERROR'] = diag['by_reason'].get('UNKNOWN_ERROR', 0) + 1
            print(f"  ⚠️ {t}: UNKNOWN_ERROR: {e}")
        if i % 400 == 0:
            print(f"  ...{i}/{len(tickers)}")
    diag['global_last_date'] = str(global_last)
    return pd.DataFrame(all_events), states, diag


# ------------------------------------------------------------------ scoring

def score(ev_df, model, spy):
    """Adds calibrated confidence + expected 20d return + drivers to ACTUAL events."""
    if ev_df.empty:
        for col in ('confidence', 'expected_ret_20d', 'drivers'):
            ev_df[col] = []
        return ev_df
    ev_df = ev_df.copy()
    if 'closed_above' in ev_df.columns and ev_df['closed_above'].dtype == object:
        ev_df['closed_above'] = (ev_df['closed_above'] == True).astype(float)
    ev_df = add_market_context(ev_df, spy)
    conf = np.full(len(ev_df), np.nan)
    exp_ret = np.full(len(ev_df), np.nan)
    drivers = [''] * len(ev_df)
    for side, key in (('upper', 'upper_breakout'), ('under', 'under_touch')):
        mask = (ev_df['side'] == key).values
        if not mask.any():
            continue
        sub = ev_df[mask]
        p_raw, X = raw_score(sub, model[side])
        p_cal = calibrated(p_raw, model[side])
        conf[mask] = np.round(p_cal * 100, 1)
        idxs = np.where(mask)[0]
        for j, gi in enumerate(idxs):
            top = contributions(X[j], model[side])[:2]
            drivers[gi] = ' · '.join(
                f"{FEATURE_LABELS_HE.get(k, k)} {'↑' if v > 0 else '↓'}" for k, v in top)
            er = expected_ret_20d(conf[gi], model[side])
            if er is not None:
                exp_ret[gi] = round(er, 2)
    ev_df['confidence'] = conf
    ev_df['expected_ret_20d'] = exp_ret
    ev_df['drivers'] = drivers
    return ev_df


# ------------------------------------------------------------------ wallet

def entry_ok(row):
    if pd.isna(row['confidence']) or row['confidence'] < CONF_MIN or row['close'] < MIN_PRICE:
        return False
    if row['side'] == 'upper_breakout':
        return row.get('attempt_no', 1) >= UPPER_MIN_ATTEMPT
    return (bool(row.get('closed_above')) and row.get('days_since_anchor', 0) >= UNDER_MIN_LINE_AGE
            and abs(row.get('slope_yr_pct', 0)) <= UNDER_MAX_SLOPE)


def _exit_levels(entry):
    assert EXIT_POLICY['kind'] == 'fixed_pct', f"exit policy '{EXIT_POLICY['kind']}' not implemented"
    return (round(entry * (1 + EXIT_POLICY['sl_pct'] / 100), 2),
            round(entry * (1 + EXIT_POLICY['tp_pct'] / 100), 2))


def _db_price_loader():
    prices = {}

    def px(ticker):
        if ticker not in prices:
            rows = db.fetch_query("""
                SELECT date, open, high, low, close FROM stock_prices
                WHERE ticker=%s AND date >= %s ORDER BY date;""", (ticker, WALLET_START.date()))
            f = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close'])
            for cc in ('open', 'high', 'low', 'close'):
                f[cc] = f[cc].astype(float)
            f['date'] = pd.to_datetime(f['date'])
            prices[ticker] = f.set_index('date')
        return prices[ticker]
    return px


def simulate_wallet(ev_df, px=None, calendar=None):
    """Bar-by-bar replay. Entries at event close; within a day, eligible signals
    are taken in confidence-DESC order. Exits: SL (takes precedence over TP when
    both are touched intraday), TP, TIME after EXIT_POLICY['time_days'] TRADING
    days on the market calendar (independent of the ticker's own bars), and
    STALE force-close after STALE_AFTER_MISSING consecutive missing bars."""
    signals = ev_df[ev_df.apply(entry_ok, axis=1)].copy()
    signals['event_date'] = pd.to_datetime(signals['event_date'])
    signals = signals[signals['event_date'] >= WALLET_START]
    # deterministic priority: date ASC, confidence DESC (ticker only as final tiebreak)
    signals = signals.sort_values(['event_date', 'confidence', 'ticker'],
                                  ascending=[True, False, True])

    if calendar is None:
        cal_rows = db.fetch_query(
            "SELECT date FROM stock_prices WHERE ticker='SPY' AND date >= %s ORDER BY date;", (WALLET_START.date(),))
        calendar = [pd.Timestamp(r[0]) for r in cal_rows]
    if px is None:
        px = _db_price_loader()

    time_days = EXIT_POLICY['time_days']
    cash = START_CASH
    open_pos = {}
    trades = []
    equity = []
    data_issues = []
    sig_by_day = {d: g for d, g in signals.groupby('event_date')}

    for day in calendar:
        # 1) exits — position clock ticks on the MARKET calendar, bar or no bar
        for tk in list(open_pos):
            pos = open_pos[tk]
            pos['days'] += 1
            p = px(tk)
            has_bar = day in p.index
            exit_price, reason = None, None

            if has_bar:
                pos['missing'] = 0
                bar = p.loc[day]
                pos['last_close'] = float(bar['close'])
                if bar['low'] <= pos['sl']:
                    exit_price, reason = pos['sl'], 'SL'      # SL precedence over TP
                elif bar['high'] >= pos['tp']:
                    exit_price, reason = pos['tp'], 'TP'
            else:
                pos['missing'] += 1
                if pos['missing'] >= STALE_AFTER_MISSING:
                    exit_price, reason = pos['last_close'], 'STALE'
                    data_issues.append(f"{tk}: no bars for {pos['missing']} trading days — "
                                       f"force-closed at last known close {pos['last_close']:.2f} on {day.date()}")

            if exit_price is None and pos['days'] >= time_days:
                exit_price, reason = pos['last_close'] if not has_bar else float(p.loc[day]['close']), 'TIME'

            if exit_price is not None:
                pnl = (exit_price - pos['entry']) * pos['qty']
                cash += pos['qty'] * exit_price
                trades.append({**{k: pos[k] for k in ('ticker', 'side', 'entry_date', 'entry', 'sl', 'tp', 'confidence')},
                               'exit_date': day.date(), 'exit': round(exit_price, 2), 'reason': reason,
                               'pnl': round(pnl, 2), 'pnl_pct': round((exit_price / pos['entry'] - 1) * 100, 2),
                               'days_held': pos['days']})
                del open_pos[tk]

        # 2) entries — highest confidence first when capacity is limited
        if day in sig_by_day:
            for _, row in sig_by_day[day].iterrows():
                tk = row['ticker']
                if tk in open_pos or len(open_pos) >= MAX_OPEN or cash < POSITION_SIZE:
                    continue
                entry = float(row['close'])
                sl, tp = _exit_levels(entry)
                qty = POSITION_SIZE / entry
                cash -= POSITION_SIZE
                open_pos[tk] = {
                    'ticker': tk, 'side': 'פריצה' if row['side'] == 'upper_breakout' else 'תמיכה',
                    'entry_date': day.date(), 'entry': entry, 'qty': qty,
                    'sl': sl, 'tp': tp, 'confidence': row['confidence'],
                    'days': 0, 'missing': 0, 'last_close': entry,
                }

        # 3) mark to market (last known close per position)
        mtm = cash
        for tk, pos in open_pos.items():
            p = px(tk)
            if day in p.index:
                pos['last_close'] = float(p.loc[day]['close'])
            mtm += pos['qty'] * pos['last_close']
        equity.append({'date': day.date(), 'equity': round(mtm, 2),
                       'open_positions': len(open_pos), 'cash': round(cash, 2)})

    open_rows = []
    for tk, pos in open_pos.items():
        open_rows.append({**{k: pos[k] for k in ('ticker', 'side', 'entry_date', 'entry', 'sl', 'tp', 'confidence')},
                          'last': round(pos['last_close'], 2),
                          'pnl_pct': round((pos['last_close'] / pos['entry'] - 1) * 100, 2),
                          'days_held': pos['days']})

    return pd.DataFrame(trades), pd.DataFrame(open_rows), pd.DataFrame(equity), data_issues


# ------------------------------------------------------------------ today's tables

STATUS_LABELS = {
    'BREAKOUT': 'פריצה', 'SUPPORT_TOUCH': 'נגיעת תמיכה',
    'PIERCED': 'חדירה — טרם אושרה', 'APPROACHING': 'מתקרב',
}


def todays_tables(ev_df, states, model, spy, recent_days=5):
    last_date = max(s['date'] for s in states.values())
    cutoff = pd.Timestamp(last_date) - pd.Timedelta(days=recent_days)

    # tickers whose data is fresh enough to appear as "today's" candidates
    fresh = {t for t, s in states.items()
             if (pd.Timestamp(last_date) - pd.Timestamp(s['date'])).days <= 5}

    ev_df = ev_df.copy()
    ev_df['event_date_ts'] = pd.to_datetime(ev_df['event_date'])
    recent = ev_df[(ev_df['event_date_ts'] >= cutoff) & (ev_df['ticker'].isin(fresh))].copy()

    def event_status(r):
        if r['side'] == 'upper_breakout':
            return 'BREAKOUT'
        return 'SUPPORT_TOUCH' if r.get('closed_above') else 'PIERCED'
    recent['status'] = recent.apply(event_status, axis=1)

    # actual events get model confidence; APPROACHING rows explicitly do NOT
    recent = score(recent, model, spy)

    approach = []
    for tk, st in states.items():
        if tk not in fresh:
            continue
        up = st.get('upper')
        if up and 0 < -up['gap_vs_line_pct'] <= 3:
            approach.append({**up, 'status': 'APPROACHING'})
        un = st.get('under')
        if un and 0 < un['gap_vs_line_pct'] <= 3:
            approach.append({**un, 'status': 'APPROACHING'})
    app_df = pd.DataFrame(approach)
    if len(app_df):
        app_df['confidence'] = np.nan          # no event probability without an event
        app_df['expected_ret_20d'] = np.nan
        app_df['drivers'] = ''

    combined = pd.concat([recent, app_df], ignore_index=True) if len(app_df) else recent
    # an actual event outranks an approaching row for the same ticker+side
    combined['is_event'] = combined['status'] != 'APPROACHING'
    combined = (combined.sort_values(['is_event'], ascending=False)
                        .drop_duplicates(subset=['ticker', 'side'], keep='first'))
    # candidates require a mature line: at least 50 trading days since anchor 2 (H2/L2)
    combined = combined[combined['days_since_anchor'] >= 50]

    upper = combined[(combined['side'] == 'upper_breakout') & (combined['close'] >= MIN_PRICE)]
    under = combined[(combined['side'] == 'under_touch') & (combined['close'] >= MIN_PRICE)
                     & (combined['slope_yr_pct'].abs() <= UNDER_MAX_SLOPE)]
    sort_cols = ['is_event', 'confidence']
    upper = upper.sort_values(sort_cols, ascending=[False, False], na_position='last')
    under = under.sort_values(sort_cols, ascending=[False, False], na_position='last')
    return upper, under, str(last_date)


def run():
    with open(MODEL_OOS_PATH) as f:
        model = json.load(f)
    # no-look-ahead guard: the wallet model must not know anything past AS_OF
    for side in ('upper', 'under'):
        assert pd.Timestamp(model[side]['calibrated_through']) < WALLET_START, \
            f"look-ahead: {side} model calibrated through {model[side]['calibrated_through']} >= WALLET_START {WALLET_START.date()}"
    spy = spy_context()

    os.makedirs('dashboard/data', exist_ok=True)
    meta = {
        'as_of': str(AS_OF.date()),
        'wallet_start': str(WALLET_START.date()),
        'run_at': datetime.now().isoformat(timespec='seconds'),
        'mode': SIMULATION_MODE,
        'model_fit_through': model['upper']['fit_through'],
        'model_calibrated_through': model['upper']['calibrated_through'],
        'wallet_universe': WALLET_UNIVERSE,
        'universes': {},
    }
    wallet_out = None
    last_date = None

    for key, table, label in UNIVERSES:
        print(f"\n### universe {key} ({label}) — simulating from {AS_OF.date()} [{SIMULATION_MODE}]...")
        ev_df, states, diag = simulate_all(table)
        print(f"{len(ev_df)} events, {len(states)} tickers with lines")
        if not states:
            print(f"  ⚠️ no data for universe {key} — skipped")
            continue

        upper, under, u_last = todays_tables(ev_df, states, model, spy)
        upper.to_csv(f'dashboard/data/table_upper_{key}.csv', index=False)
        under.to_csv(f'dashboard/data/table_under_{key}.csv', index=False)

        # recent scored events (last ~45 calendar days) for the product site's history view
        rec = ev_df[pd.to_datetime(ev_df['event_date']) >= pd.Timestamp(u_last) - pd.Timedelta(days=45)].copy()
        if len(rec):
            rec['status'] = rec.apply(
                lambda r: 'BREAKOUT' if r['side'] == 'upper_breakout'
                else ('SUPPORT_TOUCH' if r.get('closed_above') else 'PIERCED'), axis=1)
            rec = score(rec, model, spy)
            keep = ['ticker', 'side', 'event_date', 'status', 'close', 'line', 'gap_vs_line_pct',
                    'anchor1', 'anchor2', 'days_since_anchor', 'slope_yr_pct', 'vol_ratio20',
                    'atr_pct', 'dollar_vol_m', 'attempt_no', 'touch_no', 'closed_above',
                    'confidence', 'expected_ret_20d']
            rec[[c for c in keep if c in rec.columns]].to_csv(
                f'dashboard/data/events_recent_{key}.csv', index=False)
        last_date = max(last_date or u_last, u_last)
        new_events_today = int((pd.to_datetime(ev_df['event_date']).dt.date == pd.Timestamp(u_last).date()).sum())
        meta['universes'][key] = {
            'label': label, 'last_date': u_last, 'diagnostics': diag,
            'upper_candidates': len(upper), 'under_candidates': len(under),
            'new_events_today': new_events_today,
        }

        if key == WALLET_UNIVERSE:
            scored = score(ev_df, model, spy)
            wallet_out = simulate_wallet(scored)
            q_closed, q_open = build_quality_wallet(ev_df)
            q_closed.to_csv('dashboard/data/quality_trades.csv', index=False)
            q_open.to_csv('dashboard/data/quality_open.csv', index=False)
            q_eq = quality_equity_curve(pd.concat([q_closed, q_open], ignore_index=True))
            q_eq.to_csv('dashboard/data/quality_equity.csv', index=False)
            q_end = float(q_eq['equity'].iloc[-1]) if len(q_eq) else START_CASH
            meta['quality'] = {
                'closed': len(q_closed), 'open': len(q_open),
                'pnl': round(float(q_closed['pnl'].sum()), 2) if len(q_closed) else 0.0,
                'win_pct': round(float((q_closed['ret_pct'] > 0).mean() * 100), 1) if len(q_closed) else None,
                'start': str(QUALITY_START.date()),
                'equity_end': round(q_end, 2),
                'ret_pct': round((q_end / START_CASH - 1) * 100, 2),
            }

    trades, open_pos, equity, data_issues = wallet_out
    trades.to_csv('dashboard/data/trades.csv', index=False)
    open_pos.to_csv('dashboard/data/open_positions.csv', index=False)
    equity.to_csv('dashboard/data/equity.csv', index=False)

    last_ts = pd.Timestamp(last_date).date()
    entries_today = int((pd.to_datetime(open_pos['entry_date']).dt.date == last_ts).sum()) if len(open_pos) else 0
    exits_today = int((pd.to_datetime(trades['exit_date']).dt.date == last_ts).sum()) if len(trades) else 0
    meta['last_date'] = last_date
    meta['wallet_entries_today'] = entries_today
    meta['wallet_exits_today'] = exits_today
    meta['data_issues'] = data_issues
    with open('dashboard/data/meta.json', 'w') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    # ---- daily summary ----
    print("\n===== DAILY SUMMARY =====")
    print(f"latest data date : {last_date}   (run at {meta['run_at']})")
    for key, u in meta['universes'].items():
        d = u['diagnostics']
        print(f"[{key:8s}] tickers: scanned {d['scanned']}, processed {d['processed']}, issues: {d['by_reason'] or 'none'}")
        print(f"[{key:8s}] candidates: upper {u['upper_candidates']}, under {u['under_candidates']} "
              f"| new events today: {u['new_events_today']}")
    print(f"wallet ({WALLET_UNIVERSE}) : {len(trades)} closed, {len(open_pos)} open | today: +{entries_today} in / -{exits_today} out")
    if data_issues:
        print("data issues      :")
        for d in data_issues:
            print(f"  ⚠️ {d}")
    return trades, open_pos, equity, last_date


if __name__ == '__main__':
    run()
