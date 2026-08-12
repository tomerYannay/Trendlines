#!/usr/bin/env python3
"""
Test script for get_sequence_breakdown_for_filtered_upper_tickers function
"""

from db import get_sequence_breakdown_for_filtered_upper_tickers

# Test the function
result = get_sequence_breakdown_for_filtered_upper_tickers('2025-10-31', '2025-10-01', '2025-10-30')

# Print detailed results
print("\n" + "="*60)
print("DETAILED RESULTS - UPPER BREAKTHROUGH ANALYSIS")
print("="*60)

print(f"\nCheck Date: {result['check_date']}")
print(f"\nFiltered Tickers ({result['filtered_count']} total):")
if result['filtered_tickers']:
    for ticker in result['filtered_tickers']:
        ticker_info = result['ticker_distance_map'][ticker]
        print(f"  - {ticker}: distance={ticker_info['distance']}, close=${ticker_info['close']:.2f}")
else:
    print("  None")

print(f"\n\nTickers with check_date close > initial close on {result['check_date']} ({result['sequence_gt_1_count']} total):")
print("(Price increased from initial breakthrough)")
if result['sequence_gt_1_with_distance']:
    for item in result['sequence_gt_1_with_distance']:
        print(f"  - {item['ticker']}: distance={item['distance']}, close=${item['close']:.2f}")
else:
    print("  None")

print(f"\n\nTickers with sequence = 1 on {result['check_date']} ({result['sequence_eq_1_count']} total):")
print("(Still at first breakthrough)")
if result['sequence_eq_1_with_distance']:
    for item in result['sequence_eq_1_with_distance']:
        print(f"  - {item['ticker']}: distance={item['distance']}, close=${item['close']:.2f}")
else:
    print("  None")

print(f"\n\nTickers with check_date close < initial close on {result['check_date']} ({result['sequence_eq_0_count']} total):")
print("(Price decreased from initial breakthrough)")
if result['sequence_eq_0_with_distance']:
    for item in result['sequence_eq_0_with_distance']:
        print(f"  - {item['ticker']}: distance={item['distance']}, close=${item['close']:.2f}")
else:
    print("  None")

print("\n" + "="*60)
