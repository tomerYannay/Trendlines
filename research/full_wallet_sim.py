"""
Full 2020->today wallet simulation — RULES ONLY (no confidence model).

Replays the dashboard's exact line logic (anchored before 2020-01-01, evolving
with the corrected renewal rules) and trades every signal that passes the
validated entry RULES, without the ML confidence gate — because the confidence
model was trained on 2022-2026 data and cannot honestly score that period.

Entry rules (identical to the wallet, minus the confidence threshold):
  upper : breakout with attempt_no >= 2, close >= $5
  under : support bounce (closed above), line age >= 50 trading days,
          |slope| <= 100%/yr, close >= $5
Exits  : SL -10%, TP +20%, time exit 40 trading days (SL precedence intraday).

Honesty note printed with the results: 2022-mid2025 overlaps the period on
which the rules were DISCOVERED (in-sample); 2020-2021 and mid2025+ are
out-of-sample relative to rule discovery.

Usage:  python -m research.full_wallet_sim
"""
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import db
import dashboard.engine as eng

SIM_START = pd.Timestamp('2020-01-02')


def main():
    print("walking all russell tickers from 2020 (this is the slow part)...")
    ev_df, states, diag = eng.simulate_all('tickers_russell')
    print(f"{len(ev_df)} events")

    # rule-only gate: same as eng.entry_ok but without the confidence threshold
    def rule_ok(row):
        if row['close'] < eng.MIN_PRICE:
            return False
        if row['side'] == 'upper_breakout':
            return row.get('attempt_no', 1) >= eng.UPPER_MIN_ATTEMPT
        return (bool(row.get('closed_above')) and row.get('days_since_anchor', 0) >= eng.UNDER_MIN_LINE_AGE
                and abs(row.get('slope_yr_pct', 0)) <= eng.UNDER_MAX_SLOPE)

    signals = ev_df[ev_df.apply(rule_ok, axis=1)].copy()
    signals['confidence'] = 100.0   # neutral: no model ranking; ties resolved by ticker (deterministic)
    print(f"eligible signals (rules only): {len(signals)}")

    # wallet plumbing with a 2020 window (custom loaders; engine defaults start at WALLET_START)
    cal_rows = db.fetch_query(
        "SELECT date FROM stock_prices WHERE ticker='SPY' AND date >= %s ORDER BY date;", (SIM_START.date(),))
    calendar = [pd.Timestamp(r[0]) for r in cal_rows]

    prices = {}

    def px(ticker):
        if ticker not in prices:
            rows = db.fetch_query("""
                SELECT date, open, high, low, close FROM stock_prices
                WHERE ticker=%s AND date >= %s ORDER BY date;""", (ticker, SIM_START.date()))
            f = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close'])
            for cc in ('open', 'high', 'low', 'close'):
                f[cc] = f[cc].astype(float)
            f['date'] = pd.to_datetime(f['date'])
            prices[ticker] = f.set_index('date')
        return prices[ticker]

    old_start = eng.WALLET_START
    eng.WALLET_START = SIM_START
    try:
        trades, open_pos, equity, issues = eng.simulate_wallet(signals, px=px, calendar=calendar)
    finally:
        eng.WALLET_START = old_start

    trades.to_csv('research/output/full_sim_trades.csv', index=False)
    equity.to_csv('research/output/full_sim_equity.csv', index=False)

    eq = equity['equity']
    dd = (eq / eq.cummax() - 1).min() * 100
    print(f"\n===== FULL SIMULATION 2020 -> {equity['date'].iloc[-1]} (rules only, no ML gate) =====")
    print(f"trades: {len(trades)} closed, {len(open_pos)} open")
    print(f"equity: 100,000 -> {eq.iloc[-1]:,.0f}  ({(eq.iloc[-1] / 100000 - 1) * 100:+.2f}%)   max drawdown {dd:.2f}%")
    print(f"win rate {(trades['pnl'] > 0).mean() * 100:.1f}%  avg {trades['pnl_pct'].mean():+.2f}%  "
          f"median {trades['pnl_pct'].median():+.2f}%  reasons {trades['reason'].value_counts().to_dict()}")
    if issues:
        print(f"data issues (stale closes): {len(issues)}")

    # per-year breakdown + SPY benchmark
    spy_rows = db.fetch_query("SELECT date, close FROM stock_prices WHERE ticker='SPY' ORDER BY date;")
    spy = pd.DataFrame(spy_rows, columns=['date', 'close'])
    spy['close'] = spy['close'].astype(float)
    spy['date'] = pd.to_datetime(spy['date'])
    spy = spy.set_index('date')['close']

    trades['year'] = pd.to_datetime(trades['exit_date']).dt.year
    equity['year'] = pd.to_datetime(equity['date']).dt.year
    print(f"\n{'year':6s}{'trades':>8s}{'win%':>8s}{'avg%':>8s}{'wallet ret%':>13s}{'SPY ret%':>10s}   sample")
    for y, g in trades.groupby('year'):
        eq_y = equity[equity['year'] == y]['equity']
        w_ret = (eq_y.iloc[-1] / eq_y.iloc[0] - 1) * 100 if len(eq_y) > 1 else 0
        spy_y = spy[spy.index.year == y]
        s_ret = (spy_y.iloc[-1] / spy_y.iloc[0] - 1) * 100 if len(spy_y) > 1 else float('nan')
        tag = 'IN-SAMPLE (rule discovery)' if 2022 <= y <= 2024 else ('חלקי' if y == 2025 else 'OOS')
        print(f"{y:<6d}{len(g):>8d}{(g['pnl'] > 0).mean() * 100:>7.1f}%{g['pnl_pct'].mean():>+7.2f}%"
              f"{w_ret:>+12.2f}%{s_ret:>+9.2f}%   {tag}")


if __name__ == '__main__':
    main()
