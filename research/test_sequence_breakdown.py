#!/usr/bin/env python3
"""
Test script for get_sequence_breakdown_for_filtered_tickers function
"""

from db import get_sequence_breakdown_for_filtered_tickers

# Test the function
result = get_sequence_breakdown_for_filtered_tickers('2025-10-31', '2025-10-01', '2025-10-30')

# Print detailed results
print("\n" + "="*60)
print("DETAILED RESULTS")
print("="*60)

print(f"\nCheck Date: {result['check_date']}")
print(f"\nFiltered Tickers ({result['filtered_count']} total):")
if result['filtered_tickers']:
    for ticker in result['filtered_tickers']:
        print(f"  - {ticker}")
else:
    print("  None")

print(f"\n\nTickers with sequence > 0 on {result['check_date']} ({result['sequence_gt_0_count']} total):")
if result['sequence_gt_0_tickers']:
    for ticker in result['sequence_gt_0_tickers']:
        print(f"  - {ticker}")
else:
    print("  None")

print(f"\n\nTickers with sequence = 0 on {result['check_date']} ({result['sequence_eq_0_count']} total):")
if result['sequence_eq_0_tickers']:
    for ticker in result['sequence_eq_0_tickers']:
        print(f"  - {ticker}")
else:
    print("  None")

print("\n" + "="*60)
