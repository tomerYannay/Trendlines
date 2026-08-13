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
        from db import dump_profile_csv
        try:
            daily_update()
        finally:
            dump_profile_csv('profile_times.csv')

    from dashboard import engine, build
    engine.run()
    build.build()
    print("\n✅ platform refreshed — open dashboard/site/index.html")


if __name__ == '__main__':
    main()
