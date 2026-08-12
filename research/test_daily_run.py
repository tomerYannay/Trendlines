"""
Test the daily pipeline on a small subset of tickers before a full run.

Usage (from the project root):

    python -m research.test_daily_run                 # DRY RUN: 3 tickers, nothing is written to the DB
    python -m research.test_daily_run -n 10           # dry run on 10 tickers
    python -m research.test_daily_run --real          # REAL run: 3 tickers, actually writes to the DB
    python -m research.test_daily_run --real -n 10    # real run on 10 tickers
    python -m research.test_daily_run --real -t AAON AAT   # real run on specific tickers

Dry run wraps the DB connection so every commit() is a no-op and everything is
rolled back at the end — you see exactly what WOULD be written, verified with
row counts, and the database stays untouched.
"""
import argparse
import time
import warnings

warnings.filterwarnings('ignore')

import db


class NoCommitProxy:
    """Connection wrapper that swallows commit() so nothing persists."""

    def __init__(self, conn):
        self._c = conn

    def commit(self):
        pass

    def rollback(self):
        self._c.rollback()

    def __getattr__(self, name):
        return getattr(self._c, name)


def pick_tickers(n):
    db.cursor.execute("SELECT ticker FROM tickers_russell ORDER BY ticker LIMIT %s;", (n,))
    return [r[0] for r in db.cursor.fetchall()]


def report(tickers, label):
    print(f"\n=== {label} ===")
    for t in tickers:
        db.cursor.execute("SELECT MAX(date) FROM stock_prices WHERE ticker=%s;", (t,))
        last_price = db.cursor.fetchone()[0]
        db.cursor.execute("SELECT COUNT(*), MAX(date) FROM upper_status WHERE ticker=%s;", (t,))
        n_status, last_status = db.cursor.fetchone()
        db.cursor.execute("SELECT date1, date2, slope FROM upper_trendlines WHERE ticker=%s;", (t,))
        tl = db.cursor.fetchone()
        db.cursor.execute("""
            SELECT date, distance, breakthrough, sequence FROM upper_status
            WHERE ticker=%s ORDER BY date DESC LIMIT 1;
        """, (t,))
        latest = db.cursor.fetchone()
        tl_txt = f"trendline={tl[0]}→{tl[1]} slope={tl[2]:.6f}" if tl else "no trendline"
        print(f"{t:6s} prices→{last_price} | status rows={n_status} (last {last_status}) | {tl_txt}")
        if latest:
            print(f"       latest status: date={latest[0]} distance={latest[1]:.2f}% "
                  f"breakthrough={latest[2]} sequence={latest[3]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--real', action='store_true', help='actually write to the DB (default: dry run)')
    ap.add_argument('-n', type=int, default=3, help='number of tickers (default 3)')
    ap.add_argument('-t', '--tickers', nargs='+', help='explicit ticker list')
    args = ap.parse_args()

    tickers = args.tickers or pick_tickers(args.n)
    mode = 'REAL RUN (writing to DB)' if args.real else 'DRY RUN (rollback at the end)'
    print(f"Mode: {mode}")
    print(f"Tickers: {tickers}")

    real_conn = db.connection
    if not args.real:
        db.connection = NoCommitProxy(real_conn)

    t_start = time.time()

    # Same flow as daily.daily_update()
    prefetched = db.prefetch_daily_data(tickers)
    for ticker in tickers:
        print(f"\n🟡 {ticker}")
        t0 = time.perf_counter()
        try:
            updated_dates, is_new = db.updateDBWithAPI(ticker, prefetched_df=prefetched.get(ticker))
            if is_new:
                db.find_and_update_upper_trendline(ticker)
            db.update_upper_status(ticker)
            if updated_dates:
                db.check_and_update_upper_trendline(ticker, updated_dates)
            print(f"   done in {time.perf_counter() - t0:.2f}s "
                  f"({len(updated_dates)} new price rows, new_ticker={is_new})")
        except Exception as e:
            print(f"   ❌ {e}")

    print(f"\nTotal pipeline time: {time.time() - t_start:.1f}s for {len(tickers)} tickers")

    # Show what was (or would be) written
    report(tickers, "State after run (inside transaction)" if not args.real else "State after run (committed)")

    if not args.real:
        real_conn.rollback()
        db.connection = real_conn
        db.cursor.execute("SELECT COUNT(*) FROM upper_status;")
        print(f"\n↩️  Rolled back — upper_status now has {db.cursor.fetchone()[0]} rows. DB untouched.")


if __name__ == '__main__':
    main()
