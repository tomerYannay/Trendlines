#!/usr/bin/env python3
"""
Export sentiment analysis to formatted text file
"""

import pandas as pd


def export_to_text(csv_file, output_file):
    """
    Convert CSV sentiment analysis to formatted text output

    Args:
        csv_file: Input CSV file
        output_file: Output text file
    """
    df = pd.read_csv(csv_file)

    with open(output_file, 'w') as f:
        for _, row in df.iterrows():
            check_date = row['check_date']
            start_date = row['start_date']
            end_date = row['end_date']
            total = row['total_filtered_tickers']
            seq_gt_1 = row['seq_gt_1_count']
            seq_eq_1 = row['seq_eq_1_count']
            seq_eq_0 = row['seq_eq_0_count']

            # Write formatted output
            f.write("=" * 60 + "\n")
            f.write(f"Upper Breakthrough Query Results (between {start_date} and {end_date}):\n")
            f.write(f"Total filtered tickers: {total}\n")
            f.write("\n")
            f.write(f"Sequence Breakdown on {check_date}:\n")
            f.write(f"  - Tickers with sequence > 1: {seq_gt_1}\n")
            f.write(f"  - Tickers with sequence = 1: {seq_eq_1}\n")
            f.write(f"  - Tickers with sequence = 0: {seq_eq_0} (fell back below trendline)\n")
            f.write("=" * 60 + "\n")
            f.write("\n")

    print(f"✓ Exported to: {output_file}")
    print(f"  Total entries: {len(df)}")


if __name__ == "__main__":
    import sys

    csv_file = sys.argv[1] if len(sys.argv) > 1 else 'research/output/october_2025_sentiment_summary.csv'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'research/output/october_2025_sentiment_breakdown.txt'

    export_to_text(csv_file, output_file)
