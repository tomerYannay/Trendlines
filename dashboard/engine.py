"""
Dashboard engine: walk-forward simulation + confidence scoring + paper wallet.

Deterministic by design: every run re-simulates from AS_OF to the latest
trading day in the DB, so the site is always exactly "as of today" with no
incremental-state drift.

  * Lines are anchored on data before AS_OF (2025-09-01) and evolve with the
    validated renewal rules (200d / 100% / deep-failure >5%).
  * Every breakout / support-touch event is scored by the trained confidence
    model (research/output/confidence_model.json).
  * The paper wallet enters only validated setups (see ENTRY RULES below),
    with SL/TP fixed at entry, and is replayed bar by bar.
"""
import json
import os
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import trendline_core as core
from research.build_event_dataset import load, precompute, SEQ_DAYS, EXTREME_PCT, FAIL_PCT
from research.confidence import (MODEL_PATH, FEATURES, FEATURE_LABELS_HE,
                                 spy_context, add_market_context, raw_score, calibrated, contributions)

AS_OF = pd.Timestamp('2025-09-01')

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
SL_PCT = -10.0             # validated: keeps ~90% of winners, caps the tail
TP_PCT = +20.0             # 2:1 reward:risk
TIME_EXIT_DAYS = 40        # the edge accrues in 20-40 trading days


# ------------------------------------------------------------------ simulation

def walk_ticker(ticker):
    """Replays one ticker from AS_OF. Returns (events, state) where state holds
    the current line values for the 'approaching' tables."""
    df = load(ticker)
    if df is None or len(df) < 80:
        return [], None
    dates = df['date'].tolist()
    n = len(df)
    hist_n = sum(1 for d in dates if pd.Timestamp(d) < AS_OF)
    if hist_n < 80 or hist_n == n:
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

    # ---- upper line ----
    up = core.best_upper_trendline(h[:hist_n])
    if up is not None:
        i2, p2, slope = up[1], h[up[1]], up[2]
        seq, prev_bt, attempt = 0, False, 0
        for t in range(hist_n, n):
            line_t = float(np.exp(np.log(p2) + slope * (t - i2)))
            bt = c[t] > line_t
            dist = (line_t - c[t]) / c[t] * 100
            s = seq + 1 if bt else 0
            if bt and seq == 0 and c[t] >= 2.0:
                attempt += 1
                events.append(feats(t, 'upper_breakout', line_t, slope, i2, {'attempt_no': attempt}))
            flag = (s > SEQ_DAYS) or (dist > FAIL_PCT and prev_bt) or (dist < -EXTREME_PCT)
            seq, prev_bt = s, bt
            if flag:
                r = core.best_upper_trendline(h[:t + 1])
                if r is not None:
                    i2, p2, slope = r[1], h[r[1]], r[2]
                    seq, prev_bt, attempt = 0, False, 0
        t = n - 1
        line_t = float(np.exp(np.log(p2) + slope * (t - i2)))
        state['upper'] = feats(t, 'upper_breakout', line_t, slope, i2, {'attempt_no': attempt + 1})

    # ---- under line ----
    un = core.best_under_trendline(l[:hist_n])
    if un is not None:
        j2, q2, slope_u = un[1], l[un[1]], un[2]
        seq, prev_bt, touch = 0, False, 0
        last_touch = -10**9
        for t in range(hist_n, n):
            line_t = float(np.exp(np.log(q2) + slope_u * (t - j2)))
            bt = c[t] < line_t
            dist = (line_t - c[t]) / c[t] * 100
            s = seq + 1 if bt else 0
            if l[t] <= line_t and c[t] >= 2.0 and t - last_touch > 3:
                touch += 1
                events.append(feats(t, 'under_touch', line_t, slope_u, j2, {
                    'touch_no': touch,
                    'pierce_depth_pct': round((line_t - l[t]) / line_t * 100, 2),
                    'closed_above': bool(c[t] > line_t),
                }))
                last_touch = t
            flag = (s > SEQ_DAYS) or (dist > 0 and prev_bt) or (dist > EXTREME_PCT)
            seq, prev_bt = s, bt
            if flag:
                r = core.best_under_trendline(l[:t + 1])
                if r is not None:
                    j2, q2, slope_u = r[1], l[r[1]], r[2]
                    seq, prev_bt, touch = 0, False, 0
                    last_touch = -10**9
        t = n - 1
        line_t = float(np.exp(np.log(q2) + slope_u * (t - j2)))
        state['under'] = feats(t, 'under_touch', line_t, slope_u, j2, {
            'touch_no': touch + 1, 'pierce_depth_pct': 0.0, 'closed_above': True,
        })

    return events, state


def simulate_all():
    db.cursor.execute("SELECT ticker FROM tickers_russell ORDER BY ticker;")
    tickers = [r[0] for r in db.cursor.fetchall()]
    all_events, states = [], {}
    for i, t in enumerate(tickers, 1):
        try:
            evs, st = walk_ticker(t)
            all_events.extend(evs)
            if st is not None:
                states[t] = st
        except Exception:
            continue
        if i % 400 == 0:
            print(f"  ...{i}/{len(tickers)}")
    return pd.DataFrame(all_events), states


# ------------------------------------------------------------------ scoring

def score(ev_df, model, spy):
    """Adds confidence + top drivers to an events dataframe."""
    if ev_df.empty:
        ev_df['confidence'] = []
        ev_df['drivers'] = []
        return ev_df
    ev_df = ev_df.copy()
    if 'closed_above' in ev_df.columns and ev_df['closed_above'].dtype == object:
        ev_df['closed_above'] = (ev_df['closed_above'] == True).astype(float)
    ev_df = add_market_context(ev_df, spy)
    conf = np.full(len(ev_df), np.nan)
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
    ev_df['confidence'] = conf
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


def simulate_wallet(ev_df):
    """Bar-by-bar replay: entries at event close, exits at SL/TP intraday
    (SL takes precedence when both hit) or at close after TIME_EXIT_DAYS."""
    signals = ev_df[ev_df.apply(entry_ok, axis=1)].copy()
    signals['event_date'] = pd.to_datetime(signals['event_date'])
    signals = signals.sort_values(['event_date', 'ticker'])

    # trading calendar from SPY
    cal_rows = db.fetch_query("SELECT date FROM stock_prices WHERE ticker='SPY' AND date >= %s ORDER BY date;",
                              (AS_OF.date(),))
    calendar = [pd.Timestamp(r[0]) for r in cal_rows]

    prices = {}   # ticker -> DataFrame indexed by date

    def px(ticker):
        if ticker not in prices:
            rows = db.fetch_query("""
                SELECT date, open, high, low, close FROM stock_prices
                WHERE ticker=%s AND date >= %s ORDER BY date;""", (ticker, AS_OF.date()))
            f = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close'])
            for cc in ('open', 'high', 'low', 'close'):
                f[cc] = f[cc].astype(float)
            f['date'] = pd.to_datetime(f['date'])
            prices[ticker] = f.set_index('date')
        return prices[ticker]

    cash = START_CASH
    open_pos = {}     # ticker -> dict
    trades = []
    equity = []
    sig_by_day = {d: g for d, g in signals.groupby('event_date')}

    for day in calendar:
        # 1) exits
        for tk in list(open_pos):
            pos = open_pos[tk]
            p = px(tk)
            if day not in p.index:
                continue
            bar = p.loc[day]
            exit_price, reason = None, None
            if bar['low'] <= pos['sl']:
                exit_price, reason = pos['sl'], 'SL'
            elif bar['high'] >= pos['tp']:
                exit_price, reason = pos['tp'], 'TP'
            else:
                pos['days'] += 1
                if pos['days'] >= TIME_EXIT_DAYS:
                    exit_price, reason = bar['close'], 'TIME'
            if exit_price is not None:
                pnl = (exit_price - pos['entry']) * pos['qty']
                cash += pos['qty'] * exit_price
                trades.append({**{k: pos[k] for k in ('ticker', 'side', 'entry_date', 'entry', 'sl', 'tp', 'confidence')},
                               'exit_date': day.date(), 'exit': round(exit_price, 2), 'reason': reason,
                               'pnl': round(pnl, 2), 'pnl_pct': round((exit_price / pos['entry'] - 1) * 100, 2),
                               'days_held': pos['days']})
                del open_pos[tk]

        # 2) entries
        if day in sig_by_day:
            for _, row in sig_by_day[day].iterrows():
                tk = row['ticker']
                if tk in open_pos or len(open_pos) >= MAX_OPEN or cash < POSITION_SIZE:
                    continue
                entry = float(row['close'])
                qty = POSITION_SIZE / entry
                cash -= POSITION_SIZE
                open_pos[tk] = {
                    'ticker': tk, 'side': 'פריצה' if row['side'] == 'upper_breakout' else 'תמיכה',
                    'entry_date': day.date(), 'entry': entry, 'qty': qty,
                    'sl': round(entry * (1 + SL_PCT / 100), 2), 'tp': round(entry * (1 + TP_PCT / 100), 2),
                    'confidence': row['confidence'], 'days': 0,
                }

        # 3) mark to market
        mtm = cash
        for tk, pos in open_pos.items():
            p = px(tk)
            last = p.loc[:day]['close']
            if len(last):
                mtm += pos['qty'] * float(last.iloc[-1])
        equity.append({'date': day.date(), 'equity': round(mtm, 2), 'open_positions': len(open_pos), 'cash': round(cash, 2)})

    # open positions marked at last close
    open_rows = []
    for tk, pos in open_pos.items():
        p = px(tk)
        last_close = float(p['close'].iloc[-1])
        open_rows.append({**{k: pos[k] for k in ('ticker', 'side', 'entry_date', 'entry', 'sl', 'tp', 'confidence')},
                          'last': round(last_close, 2),
                          'pnl_pct': round((last_close / pos['entry'] - 1) * 100, 2),
                          'days_held': pos['days']})

    return pd.DataFrame(trades), pd.DataFrame(open_rows), pd.DataFrame(equity)


# ------------------------------------------------------------------ today's tables

def todays_tables(ev_df, states, model, spy, recent_days=5):
    last_date = max(s['date'] for s in states.values())
    cutoff = pd.Timestamp(last_date) - pd.Timedelta(days=recent_days)

    ev_df = ev_df.copy()
    ev_df['event_date_ts'] = pd.to_datetime(ev_df['event_date'])
    recent = ev_df[ev_df['event_date_ts'] >= cutoff].copy()
    recent['status'] = recent['event_date'].astype(str)

    # approaching: hypothetical event at today's bar, within 3% of the line
    approach = []
    for tk, st in states.items():
        up = st.get('upper')
        if up and 0 < -up['gap_vs_line_pct'] <= 3:      # close is 0-3% below the line
            approach.append({**up, 'status': 'מתקרב'})
        un = st.get('under')
        if un and 0 < un['gap_vs_line_pct'] <= 3:       # close is 0-3% above the line
            approach.append({**un, 'status': 'מתקרב'})
    app_df = pd.DataFrame(approach)

    combined = pd.concat([recent, app_df], ignore_index=True) if len(app_df) else recent
    combined = combined.drop_duplicates(subset=['ticker', 'side'], keep='first')
    combined = score(combined, model, spy)

    upper = combined[(combined['side'] == 'upper_breakout') & (combined['close'] >= MIN_PRICE)]
    under = combined[(combined['side'] == 'under_touch') & (combined['close'] >= MIN_PRICE)
                     & (combined['slope_yr_pct'].abs() <= UNDER_MAX_SLOPE)]
    upper = upper.sort_values('confidence', ascending=False)
    under = under.sort_values('confidence', ascending=False)
    return upper, under, str(last_date)


def run():
    print(f"simulating from {AS_OF.date()}...")
    ev_df, states = simulate_all()
    print(f"{len(ev_df)} events, {len(states)} tickers with lines")

    with open(MODEL_PATH) as f:
        model = json.load(f)
    spy = spy_context()

    scored = score(ev_df, model, spy)
    trades, open_pos, equity = simulate_wallet(scored)
    upper, under, last_date = todays_tables(ev_df, states, model, spy)

    os.makedirs('dashboard/data', exist_ok=True)
    trades.to_csv('dashboard/data/trades.csv', index=False)
    open_pos.to_csv('dashboard/data/open_positions.csv', index=False)
    equity.to_csv('dashboard/data/equity.csv', index=False)
    upper.to_csv('dashboard/data/table_upper.csv', index=False)
    under.to_csv('dashboard/data/table_under.csv', index=False)
    with open('dashboard/data/meta.json', 'w') as f:
        json.dump({'last_date': last_date, 'as_of': str(AS_OF.date()),
                   'events': len(ev_df)}, f)
    print(f"wallet: {len(trades)} closed trades, {len(open_pos)} open | data as of {last_date}")
    return trades, open_pos, equity, upper, under, last_date


if __name__ == '__main__':
    run()
