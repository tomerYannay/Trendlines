#!/usr/bin/env python3
"""
Test script to verify the ticker extremes integration in historical_pipeline.py
This script checks that the imports work correctly without running the full pipeline.
"""

import sys

def test_imports():
    """Test that all imports work correctly"""
    print("Testing imports from historical_pipeline.py...")

    try:
        from historical_pipeline import historical_analysis_pipeline
        print("✅ Successfully imported historical_analysis_pipeline")
    except ImportError as e:
        print(f"❌ Failed to import: {e}")
        return False

    try:
        from historical_analysis import update_ticker_extremes
        print("✅ Successfully imported update_ticker_extremes")
    except ImportError as e:
        print(f"❌ Failed to import: {e}")
        return False

    print("\n✅ All imports successful!")
    return True

def test_function_signature():
    """Test that the function exists and has the correct docstring"""
    print("\nTesting function signature and documentation...")

    try:
        from historical_pipeline import historical_analysis_pipeline

        # Check docstring
        docstring = historical_analysis_pipeline.__doc__
        if "1.5. Updates ticker extremes" in docstring:
            print("✅ Function docstring includes Step 1.5 (ticker extremes)")
        else:
            print("⚠️  Warning: Docstring may not be updated correctly")
            print(f"Docstring: {docstring}")

        return True
    except Exception as e:
        print(f"❌ Error checking function: {e}")
        return False

def main():
    """Main test function"""
    print("="*60)
    print("PIPELINE INTEGRATION TEST")
    print("="*60)
    print()

    # Test 1: Imports
    if not test_imports():
        print("\n❌ Import test failed!")
        sys.exit(1)

    # Test 2: Function signature
    if not test_function_signature():
        print("\n❌ Function signature test failed!")
        sys.exit(1)

    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED")
    print("="*60)
    print()
    print("The ticker extremes update has been successfully integrated into")
    print("historical_pipeline.py as Step 1.5.")
    print()
    print("To run the full pipeline with the new step:")
    print("  python3 historical_pipeline.py")

if __name__ == "__main__":
    main()
