#!/usr/bin/env python3
"""
October Sentiment Analysis - Track sequence and distance changes over the month

This script loops through October with the following pattern:
- start_date: always '2024-10-01' (fixed)
- end_date: increments from '2024-10-02' to '2024-10-30'
- check_date: increments from '2024-10-03' to '2024-10-31'

For each check_date, it analyzes:
1. How many tickers have sequence > 1
2. How many tickers have sequence = 0
3. Ticker names in each team
4. Distances from trendline for each ticker
5. Average distance for each team
"""

import pandas as pd
from datetime import datetime, timedelta
from db import get_sequence_breakdown_for_filtered_upper_tickers
import csv


def generate_october_dates(year=2025):
    """
    Generate date combinations for October analysis with EXPANDING window

    FIXED start_date at 2025-09-01, with end_date and check_date incrementing:
    - start_date: ALWAYS '2025-09-01' (FIXED!)
    - end_date: increments from '2025-09-01' to '2025-10-30'
    - check_date: increments from '2025-09-02' to '2025-10-31' (always 1 day after end_date)

    Example:
    - Iteration 1: start='2025-09-01', end='2025-09-01', check='2025-09-02'
    - Iteration 2: start='2025-09-01', end='2025-09-02', check='2025-09-03'
    - Iteration 3: start='2025-09-01', end='2025-09-03', check='2025-09-04'
    - ...
    - Last: start='2025-09-01', end='2025-10-30', check='2025-10-31'

    This creates an expanding query window from the fixed start date.

    Returns:
        List of tuples: (start_date, end_date, check_date)
    """
    date_combinations = []

    # FIXED start date - never changes!
    start_date_fixed = datetime(year, 9, 1)

    # end_date starts at 2025-09-01 and increments
    end_date_obj = datetime(year, 9, 1)

    while True:
        # check_date is always 1 day after end_date
        check_date_obj = end_date_obj + timedelta(days=1)

        # Stop when check_date exceeds October 31
        if check_date_obj > datetime(year, 10, 31):
            break

        date_combinations.append((
            start_date_fixed.strftime('%Y-%m-%d'),  # Always 2025-09-01
            end_date_obj.strftime('%Y-%m-%d'),       # Increments
            check_date_obj.strftime('%Y-%m-%d')      # Increments (1 day after end)
        ))

        # Increment end_date for next iteration
        end_date_obj += timedelta(days=1)

    return date_combinations


def calculate_team_stats(tickers_with_distance):
    """
    Calculate statistics for a team of tickers

    Args:
        tickers_with_distance: List of dicts with 'ticker' and 'distance'

    Returns:
        dict with count, avg_distance, tickers_list
    """
    if not tickers_with_distance:
        return {
            'count': 0,
            'avg_distance': 0.0,
            'tickers': ''
        }

    distances = [t['distance'] for t in tickers_with_distance]
    tickers = [t['ticker'] for t in tickers_with_distance]

    return {
        'count': len(tickers),
        'avg_distance': sum(distances) / len(distances),
        'tickers': ','.join(tickers)
    }


def analyze_october_sentiment(year=2025, output_csv='research/output/october_sentiment_results.csv'):
    """
    Run the full October sentiment analysis and export to CSV

    Args:
        year: Year to analyze (default: 2024)
        output_csv: Output CSV filename
    """
    print(f"\n{'='*70}")
    print(f"OCTOBER {year} SENTIMENT ANALYSIS")
    print(f"{'='*70}\n")

    date_combinations = generate_october_dates(year)

    print(f"Total iterations: {len(date_combinations)}")
    print(f"Date range: {date_combinations[0][2]} to {date_combinations[-1][2]}\n")

    # Prepare CSV data
    results = []

    for idx, (start_date, end_date, check_date) in enumerate(date_combinations, 1):
        print(f"\n[{idx}/{len(date_combinations)}] Processing check_date: {check_date}")
        print(f"    Filter window: {start_date} to {end_date}")

        try:
            # Get upper trendline (resistance) breakthrough data
            result = get_sequence_breakdown_for_filtered_upper_tickers(
                check_date=check_date,
                start_date=start_date,
                end_date=end_date
            )

            # Calculate statistics for each team
            seq_gt_1_stats = calculate_team_stats(result.get('sequence_gt_1_with_distance', []))
            seq_eq_1_stats = calculate_team_stats(result.get('sequence_eq_1_with_distance', []))
            seq_eq_0_stats = calculate_team_stats(result.get('sequence_eq_0_with_distance', []))

            # Prepare row data
            row = {
                'check_date': check_date,
                'start_date': start_date,
                'end_date': end_date,
                'total_filtered_tickers': result['filtered_count'],

                # Sequence > 1 (Continued breakthrough momentum)
                'seq_gt_1_count': seq_gt_1_stats['count'],
                'seq_gt_1_avg_distance': round(seq_gt_1_stats['avg_distance'], 2),
                'seq_gt_1_tickers': seq_gt_1_stats['tickers'],

                # Sequence = 1 (First breakthrough)
                'seq_eq_1_count': seq_eq_1_stats['count'],
                'seq_eq_1_avg_distance': round(seq_eq_1_stats['avg_distance'], 2),
                'seq_eq_1_tickers': seq_eq_1_stats['tickers'],

                # Sequence = 0 (Failed breakthrough)
                'seq_eq_0_count': seq_eq_0_stats['count'],
                'seq_eq_0_avg_distance': round(seq_eq_0_stats['avg_distance'], 2),
                'seq_eq_0_tickers': seq_eq_0_stats['tickers'],

                # Sentiment indicators
                'breakthrough_momentum_pct': round((seq_gt_1_stats['count'] / max(result['filtered_count'], 1)) * 100, 1),
                'failed_breakthrough_pct': round((seq_eq_0_stats['count'] / max(result['filtered_count'], 1)) * 100, 1)
            }

            results.append(row)

            print(f"    ✓ seq > 1: {seq_gt_1_stats['count']} ({row['breakthrough_momentum_pct']}%)")
            print(f"    ✓ seq = 1: {seq_eq_1_stats['count']}")
            print(f"    ✓ seq = 0: {seq_eq_0_stats['count']} ({row['failed_breakthrough_pct']}%)")

        except Exception as e:
            print(f"    ✗ Error: {e}")
            # Add empty row to maintain sequence
            row = {
                'check_date': check_date,
                'start_date': start_date,
                'end_date': end_date,
                'total_filtered_tickers': 0,
                'seq_gt_1_count': 0,
                'seq_gt_1_avg_distance': 0.0,
                'seq_gt_1_tickers': '',
                'seq_eq_1_count': 0,
                'seq_eq_1_avg_distance': 0.0,
                'seq_eq_1_tickers': '',
                'seq_eq_0_count': 0,
                'seq_eq_0_avg_distance': 0.0,
                'seq_eq_0_tickers': '',
                'breakthrough_momentum_pct': 0.0,
                'failed_breakthrough_pct': 0.0
            }
            results.append(row)

    # Write to CSV
    if results:
        df = pd.DataFrame(results)
        df.to_csv(output_csv, index=False)
        print(f"\n{'='*70}")
        print(f"✓ Results exported to: {output_csv}")
        print(f"  Total rows: {len(results)}")
        print(f"{'='*70}\n")

        # Print summary statistics
        print("\nSUMMARY STATISTICS:")
        print(f"  Average breakthrough momentum %: {df['breakthrough_momentum_pct'].mean():.1f}%")
        print(f"  Average failed breakthrough %: {df['failed_breakthrough_pct'].mean():.1f}%")
        print(f"  Peak momentum date: {df.loc[df['breakthrough_momentum_pct'].idxmax(), 'check_date']}")
        print(f"  Peak failure date: {df.loc[df['failed_breakthrough_pct'].idxmax(), 'check_date']}")
        print()
    else:
        print("\n✗ No results to export")


def export_detailed_ticker_breakdown(year=2025, output_csv='research/output/october_ticker_details.csv'):
    """
    Export detailed per-ticker breakdown with distances for each date

    This creates a more detailed CSV with one row per ticker per date
    """
    print(f"\n{'='*70}")
    print(f"EXPORTING DETAILED TICKER BREAKDOWN")
    print(f"{'='*70}\n")

    date_combinations = generate_october_dates(year)

    # Prepare detailed CSV data
    detailed_results = []

    for idx, (start_date, end_date, check_date) in enumerate(date_combinations, 1):
        print(f"[{idx}/{len(date_combinations)}] Processing {check_date}...")

        try:
            result = get_sequence_breakdown_for_filtered_upper_tickers(
                check_date=check_date,
                start_date=start_date,
                end_date=end_date
            )

            # Add each ticker as a separate row
            for ticker_data in result.get('sequence_gt_1_with_distance', []):
                detailed_results.append({
                    'check_date': check_date,
                    'ticker': ticker_data['ticker'],
                    'team': 'seq_gt_1',
                    'sequence': '>1',
                    'distance': round(ticker_data['distance'], 2),
                    'close_price': ticker_data.get('close', '')
                })

            for ticker_data in result.get('sequence_eq_1_with_distance', []):
                detailed_results.append({
                    'check_date': check_date,
                    'ticker': ticker_data['ticker'],
                    'team': 'seq_eq_1',
                    'sequence': '1',
                    'distance': round(ticker_data['distance'], 2),
                    'close_price': ticker_data.get('close', '')
                })

            for ticker_data in result.get('sequence_eq_0_with_distance', []):
                detailed_results.append({
                    'check_date': check_date,
                    'ticker': ticker_data['ticker'],
                    'team': 'seq_eq_0',
                    'sequence': '0',
                    'distance': round(ticker_data['distance'], 2),
                    'close_price': ticker_data.get('close', '')
                })

        except Exception as e:
            print(f"    ✗ Error: {e}")

    # Write detailed CSV
    if detailed_results:
        df = pd.DataFrame(detailed_results)
        df.to_csv(output_csv, index=False)
        print(f"\n{'='*70}")
        print(f"✓ Detailed results exported to: {output_csv}")
        print(f"  Total ticker-date combinations: {len(detailed_results)}")
        print(f"{'='*70}\n")
    else:
        print("\n✗ No detailed results to export")


if __name__ == "__main__":
    import sys

    # Allow year to be specified as command line argument
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2025

    print(f"\nStarting October {year} Sentiment Analysis...")

    # Run both analyses
    analyze_october_sentiment(year=year, output_csv=f'research/output/october_{year}_sentiment_summary.csv')
    export_detailed_ticker_breakdown(year=year, output_csv=f'research/output/october_{year}_ticker_details.csv')

    print("\n✓ Analysis complete!")
