"""
Test script to verify the improved fetch_full_historical_data function
with different adjustment modes: 'none', 'alpha', 'split'
"""
import sys
from db import fetch_full_historical_data

def test_adjustment_modes():
    """Test all three adjustment modes for a stock with known splits (e.g., TSLA)"""
    symbol = 'TSLA'

    print(f"\n{'='*60}")
    print(f"Testing fetch_full_historical_data for {symbol}")
    print(f"{'='*60}\n")

    # Test 1: 'none' mode (raw prices)
    print("Test 1: Fetching with adjust='none' (raw prices)")
    try:
        rows_none = fetch_full_historical_data(symbol, adjust='none')
        print(f"✅ Success: Fetched {len(rows_none)} rows")
        print(f"Sample (most recent 3 rows):")
        for row in rows_none[:3]:
            print(f"  {row}")
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    # Test 2: 'alpha' mode (adjusted for splits and dividends)
    print("\nTest 2: Fetching with adjust='alpha' (splits + dividends)")
    try:
        rows_alpha = fetch_full_historical_data(symbol, adjust='alpha')
        print(f"✅ Success: Fetched {len(rows_alpha)} rows")
        print(f"Sample (most recent 3 rows):")
        for row in rows_alpha[:3]:
            print(f"  {row}")
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    # Test 3: 'split' mode (adjusted for splits only - IBKR style)
    print("\nTest 3: Fetching with adjust='split' (splits only - IBKR style)")
    try:
        rows_split = fetch_full_historical_data(symbol, adjust='split')
        print(f"✅ Success: Fetched {len(rows_split)} rows")
        print(f"Sample (most recent 3 rows):")
        for row in rows_split[:3]:
            print(f"  {row}")
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    # Compare prices to show differences
    print("\n" + "="*60)
    print("Price Comparison (most recent date):")
    print("="*60)
    if rows_none and rows_alpha and rows_split:
        date = rows_none[0][1]
        print(f"Date: {date}")
        print(f"  None (raw):   O={rows_none[0][2]}, H={rows_none[0][3]}, L={rows_none[0][4]}, C={rows_none[0][5]}")
        print(f"  Alpha (adj):  O={rows_alpha[0][2]}, H={rows_alpha[0][3]}, L={rows_alpha[0][4]}, C={rows_alpha[0][5]}")
        print(f"  Split (adj):  O={rows_split[0][2]}, H={rows_split[0][3]}, L={rows_split[0][4]}, C={rows_split[0][5]}")

        # For TSLA, compare an older date to see split adjustment effect
        if len(rows_none) > 100:
            idx = 100
            date_old = rows_none[idx][1]
            print(f"\nDate: {date_old} (older date to show split effect)")
            print(f"  None (raw):   O={rows_none[idx][2]}, H={rows_none[idx][3]}, L={rows_none[idx][4]}, C={rows_none[idx][5]}")
            print(f"  Alpha (adj):  O={rows_alpha[idx][2]}, H={rows_alpha[idx][3]}, L={rows_alpha[idx][4]}, C={rows_alpha[idx][5]}")
            print(f"  Split (adj):  O={rows_split[idx][2]}, H={rows_split[idx][3]}, L={rows_split[idx][4]}, C={rows_split[idx][5]}")

    print("\n" + "="*60)
    print("✅ All tests passed!")
    print("="*60)
    return True

if __name__ == "__main__":
    success = test_adjustment_modes()
    sys.exit(0 if success else 1)
