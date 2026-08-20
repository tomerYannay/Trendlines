"""
One-command daily refresh for the Trendlines platform.

    python -m dashboard.daily              # full: fetch new prices, then rebuild everything
    python -m dashboard.daily --no-fetch   # rebuild only (prices already updated today)

Steps:
  1. daily_update()            — fetch new prices for all tickers, maintain the diagonals (skippable)
  2. dashboard.engine.run()    — re-simulate events, confidence, wallet from AS_OF to today
  3. dashboard.build.build()   — regenerate dashboard/site/*.html

Then open dashboard/site/index.html in a browser (or serve the folder:
    python -m http.server 8600 --directory dashboard/site
and browse to http://localhost:8600).
"""
import argparse
import warnings

warnings.filterwarnings('ignore')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-fetch', action='store_true', help='skip the API price update')
    args = ap.parse_args()

    if not args.no_fetch:
        from daily import daily_update
        import db
        from db import dump_profile_csv
        db.cursor.execute("""
            SELECT ticker FROM tickers_russell
            UNION SELECT ticker FROM tickers_sp500
            UNION SELECT ticker FROM tickers_nasdaq
            UNION SELECT 'SPY';
        """)
        universe = [r[0] for r in db.cursor.fetchall()]
        try:
            daily_update(tickers=universe)
        finally:
            dump_profile_csv('profile_times.csv')

    # data-sanity gate: delete vendor bad prints (one-day spikes that fully
    # revert next day) before simulating — they fabricate breakouts/touches
    import db as _db
    _db.cursor.execute("""
        WITH x AS (
          SELECT ticker, date, close,
            LAG(close)  OVER (PARTITION BY ticker ORDER BY date) AS prev,
            LEAD(close) OVER (PARTITION BY ticker ORDER BY date) AS next
          FROM stock_prices)
        DELETE FROM stock_prices sp USING x
        WHERE sp.ticker = x.ticker AND sp.date = x.date
          AND x.prev > 0 AND x.next > 0 AND x.close > 0
          AND ((x.close/x.prev > 3 AND x.next/x.close < 0.4)
            OR (x.close/x.prev < 0.333 AND x.next/x.close > 2.5));""")
    if _db.cursor.rowcount:
        print(f"sanity gate: removed {_db.cursor.rowcount} bad price prints")
    _db.connection.commit()

    from dashboard import engine, build
    engine.run()
    build.build()

    # public product site — signal tables, per-ticker pages, daily "since signal" returns
    from product import build as product_build
    product_build.main()
    print("\n✅ platform refreshed — open dashboard/site/index.html")


if __name__ == '__main__':
    main()
