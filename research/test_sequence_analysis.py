#!/usr/bin/env python3
"""
Interactive test script for both sequence breakdown methods
Tests both lower (support) and upper (resistance) trendline analysis
"""

import sys
from db import get_sequence_breakdown_for_filtered_tickers, get_sequence_breakdown_for_filtered_upper_tickers

def print_separator():
    print("\n" + "="*70)

def print_lower_results(result):
    """Print results for lower trendline (support) analysis"""
    print_separator()
    print("LOWER TRENDLINE (SUPPORT) ANALYSIS - DETAILED RESULTS")
    print_separator()

    print(f"\nCheck Date: {result['check_date']}")
    print(f"\nFiltered Tickers Meeting Criteria: {result['filtered_count']} total")

    if result['filtered_tickers']:
        print("\nAll Filtered Tickers:")
        for i, ticker in enumerate(result['filtered_tickers'], 1):
            print(f"  {i:2d}. {ticker}")
    else:
        print("  None")

    print(f"\n\n--- Sequence Status on {result['check_date']} ---")

    print(f"\n✓ Tickers with sequence > 0 ({result['sequence_gt_0_count']} - {result['sequence_gt_0_count']/max(result['filtered_count'],1)*100:.1f}%):")
    print("  (Broke below trendline)")
    if result['sequence_gt_0_tickers']:
        for ticker in result['sequence_gt_0_tickers']:
            print(f"    - {ticker}")
    else:
        print("    None")

    print(f"\n✓ Tickers with sequence = 0 ({result['sequence_eq_0_count']} - {result['sequence_eq_0_count']/max(result['filtered_count'],1)*100:.1f}%):")
    print("  (Still respecting trendline)")
    if result['sequence_eq_0_tickers']:
        for ticker in result['sequence_eq_0_tickers']:
            print(f"    - {ticker}")
    else:
        print("    None")

def print_upper_results(result):
    """Print results for upper trendline (resistance) analysis"""
    print_separator()
    print("UPPER TRENDLINE (RESISTANCE) ANALYSIS - DETAILED RESULTS")
    print_separator()

    print(f"\nCheck Date: {result['check_date']}")
    print(f"\nFiltered Tickers Meeting Criteria: {result['filtered_count']} total")

    if result['filtered_tickers']:
        print("\nAll Filtered Tickers:")
        for i, ticker in enumerate(result['filtered_tickers'], 1):
            print(f"  {i:2d}. {ticker}")
    else:
        print("  None")

    print(f"\n\n--- Sequence Status on {result['check_date']} ---")

    print(f"\n✓ Tickers with sequence > 1 ({result['sequence_gt_1_count']} - {result['sequence_gt_1_count']/max(result['filtered_count'],1)*100:.1f}%):")
    print("  (Continued breakthrough momentum)")
    if result['sequence_gt_1_tickers']:
        for ticker in result['sequence_gt_1_tickers']:
            print(f"    - {ticker}")
    else:
        print("    None")

    print(f"\n✓ Tickers with sequence = 1 ({result['sequence_eq_1_count']} - {result['sequence_eq_1_count']/max(result['filtered_count'],1)*100:.1f}%):")
    print("  (Still at first breakthrough)")
    if result['sequence_eq_1_tickers']:
        for ticker in result['sequence_eq_1_tickers']:
            print(f"    - {ticker}")
    else:
        print("    None")

    print(f"\n✓ Tickers with sequence = 0 ({result['sequence_eq_0_count']} - {result['sequence_eq_0_count']/max(result['filtered_count'],1)*100:.1f}%):")
    print("  (Fell back below trendline - breakthrough failed)")
    if result['sequence_eq_0_tickers']:
        for ticker in result['sequence_eq_0_tickers']:
            print(f"    - {ticker}")
    else:
        print("    None")

def main():
    print("\n" + "="*70)
    print("TRENDLINE SEQUENCE BREAKDOWN ANALYSIS")
    print("="*70)

    # Get user inputs
    if len(sys.argv) >= 4:
        # Command line arguments provided
        check_date = sys.argv[1]
        start_date = sys.argv[2]
        end_date = sys.argv[3]
        print(f"\nUsing command line arguments:")
        print(f"  Check Date: {check_date}")
        print(f"  Start Date: {start_date}")
        print(f"  End Date: {end_date}")
    else:
        # Interactive mode
        print("\nEnter dates in format: YYYY-MM-DD")
        print("\nExample: 2025-10-31")

        check_date = input("\nCheck Date (date to analyze sequence breakdown): ").strip()
        start_date = input("Start Date (filter range start, default=2025-10-01): ").strip() or '2025-10-01'
        end_date = input("End Date (filter range end, default=check_date): ").strip() or None

    print("\n" + "="*70)
    print("RUNNING ANALYSIS...")
    print("="*70)

    # Run lower trendline (support) analysis
    print("\n[1/2] Analyzing Lower Trendline (Support) Touches...")
    try:
        lower_result = get_sequence_breakdown_for_filtered_tickers(
            check_date=check_date,
            start_date=start_date,
            end_date=end_date
        )
        print_lower_results(lower_result)
    except Exception as e:
        print(f"\n❌ Error in lower trendline analysis: {e}")

    # Run upper trendline (resistance) analysis
    print("\n[2/2] Analyzing Upper Trendline (Resistance) Breakthroughs...")
    try:
        upper_result = get_sequence_breakdown_for_filtered_upper_tickers(
            check_date=check_date,
            start_date=start_date,
            end_date=end_date
        )
        print_upper_results(upper_result)
    except Exception as e:
        print(f"\n❌ Error in upper trendline analysis: {e}")

    # Summary comparison
    print_separator()
    print("SUMMARY COMPARISON")
    print_separator()
    try:
        print(f"\nLower Trendline (Support):")
        print(f"  Total candidates: {lower_result['filtered_count']}")
        print(f"  Broke down (seq>0): {lower_result['sequence_gt_0_count']} ({lower_result['sequence_gt_0_count']/max(lower_result['filtered_count'],1)*100:.1f}%)")
        print(f"  Held support (seq=0): {lower_result['sequence_eq_0_count']} ({lower_result['sequence_eq_0_count']/max(lower_result['filtered_count'],1)*100:.1f}%)")

        print(f"\nUpper Trendline (Resistance):")
        print(f"  Total candidates: {upper_result['filtered_count']}")
        print(f"  Continued up (seq>1): {upper_result['sequence_gt_1_count']} ({upper_result['sequence_gt_1_count']/max(upper_result['filtered_count'],1)*100:.1f}%)")
        print(f"  Still at breakthrough (seq=1): {upper_result['sequence_eq_1_count']} ({upper_result['sequence_eq_1_count']/max(upper_result['filtered_count'],1)*100:.1f}%)")
        print(f"  Failed/fell back (seq=0): {upper_result['sequence_eq_0_count']} ({upper_result['sequence_eq_0_count']/max(upper_result['filtered_count'],1)*100:.1f}%)")
    except:
        pass

    print_separator()
    print("ANALYSIS COMPLETE")
    print_separator()
    print()

if __name__ == "__main__":
    main()
