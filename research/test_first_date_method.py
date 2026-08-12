"""
Test script for find_and_update_upper_trendline_historical_with_first_date method
"""
import psycopg2
from dotenv import load_dotenv
import os
from historical_analysis import find_and_update_upper_trendline_historical_with_first_date

# Load environment variables
load_dotenv()

# Database configuration
db_config = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def get_db_connection():
    """Get a new database connection"""
    return psycopg2.connect(**db_config)

def clear_previous_test_data(stock, analysis_date):
    """Clear any previous test data for this specific analysis"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM upper_trendlines_historical
            WHERE ticker = %s AND analysis_date = %s;
        """, (stock, analysis_date))
        connection.commit()
        deleted_count = cursor.rowcount
        if deleted_count > 0:
            print(f"Cleared {deleted_count} previous test record(s) for {stock} with analysis_date {analysis_date}")
    except Exception as e:
        connection.rollback()
        print(f"Error clearing previous data: {e}")
    finally:
        cursor.close()
        connection.close()

def display_trendline_result(stock, analysis_date):
    """Query and display the trendline result"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT ticker, analysis_date, date1, date2, slope, date_diff, index2
            FROM upper_trendlines_historical
            WHERE ticker = %s AND analysis_date = %s;
        """, (stock, analysis_date))

        result = cursor.fetchone()

        if result:
            ticker, analysis_date, date1, date2, slope, date_diff, index2 = result
            print("\n" + "="*60)
            print("TRENDLINE RESULT")
            print("="*60)
            print(f"Ticker:         {ticker}")
            print(f"Analysis Date:  {analysis_date}")
            print(f"Date1 (Peak 1): {date1}")
            print(f"Date2 (Peak 2): {date2}")
            print(f"Slope:          {slope:.6f}")
            print(f"Date Diff:      {date_diff} trading days")
            print(f"Index2:         {index2}")
            print("="*60)

            # Also fetch the actual high prices for these dates
            cursor.execute("""
                SELECT date, high
                FROM stock_prices
                WHERE ticker = %s AND date IN (%s, %s)
                ORDER BY date;
            """, (stock, date1, date2))

            prices = cursor.fetchall()
            if prices:
                print("\nPRICE DETAILS:")
                for date, high in prices:
                    print(f"  {date}: High = ${high:.2f}")
                print("="*60 + "\n")
        else:
            print(f"\nNo trendline found in database for {stock} with analysis_date {analysis_date}")

    except Exception as e:
        print(f"Error retrieving trendline result: {e}")
    finally:
        cursor.close()
        connection.close()

def main():
    stock = 'AAON'
    first_date = '2025-05-23'  # 100 trading days before max date
    last_date = '2025-10-15'   # Max date in database

    print(f"Testing find_and_update_upper_trendline_historical_with_first_date")
    print(f"Stock: {stock}")
    print(f"First Date: {first_date}")
    print(f"Last Date:  {last_date}")
    print("-" * 60)

    # Clear any previous test data
    clear_previous_test_data(stock, last_date)

    # Run the method
    print(f"\nRunning trendline calculation...")
    try:
        find_and_update_upper_trendline_historical_with_first_date(stock, first_date, last_date)
    except Exception as e:
        print(f"Error running method: {e}")
        return

    # Display the result
    display_trendline_result(stock, last_date)

if __name__ == "__main__":
    main()
