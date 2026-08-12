import requests
import matplotlib.pyplot as plt
from datetime import datetime
import csv

# Configuration
INITIAL_INVESTMENT = 10000
START_DATE = "2022-01-01"
END_DATE = "2026-01-01"
import os
from dotenv import load_dotenv
load_dotenv()
API_URL = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=TQQQ&outputsize=full&apikey={os.getenv('ALPHA_VANTAGE_KEY')}"

def fetch_tqqq_data():
    """Fetch TQQQ historical data from Alpha Vantage"""
    print("Fetching TQQQ data from Alpha Vantage...")
    response = requests.get(API_URL)
    data = response.json()

    if "Time Series (Daily)" not in data:
        print("Error fetching data:", data)
        return None

    return data["Time Series (Daily)"]

def simulate_investment(price_data):
    """Simulate the investment from START_DATE to END_DATE"""
    # Convert to list of (date, adjusted_close) tuples and sort by date
    prices = []
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")
    end_dt = datetime.strptime(END_DATE, "%Y-%m-%d")

    for date_str, daily_data in price_data.items():
        date = datetime.strptime(date_str, "%Y-%m-%d")
        if start_dt <= date <= end_dt:
            adjusted_close = float(daily_data["5. adjusted close"])
            prices.append((date, adjusted_close))

    # Sort by date (oldest first)
    prices.sort(key=lambda x: x[0])

    if not prices:
        print("No data available for the specified date range")
        return None, None

    # Calculate number of shares purchased on first day
    first_date, first_price = prices[0]
    shares = INITIAL_INVESTMENT / first_price

    print(f"Investment Start: {first_date.strftime('%Y-%m-%d')}")
    print(f"Initial Price: ${first_price:.2f}")
    print(f"Shares Purchased: {shares:.4f}")
    print(f"Initial Investment: ${INITIAL_INVESTMENT:.2f}")
    print()

    # Calculate portfolio value over time
    dates = []
    portfolio_values = []
    min_value = float('inf')
    min_date = None

    for date, price in prices:
        portfolio_value = shares * price
        dates.append(date)
        portfolio_values.append(portfolio_value)

        # Track minimum value
        if portfolio_value < min_value:
            min_value = portfolio_value
            min_date = date

        # Stop if portfolio reaches 0
        if portfolio_value <= 0:
            print(f"Portfolio reached $0 on {date.strftime('%Y-%m-%d')}")
            break

    # Print statistics
    final_date = dates[-1]
    final_value = portfolio_values[-1]
    print(f"Final Date: {final_date.strftime('%Y-%m-%d')}")
    print(f"Final Portfolio Value: ${final_value:,.2f}")
    print(f"Total Return: {((final_value - INITIAL_INVESTMENT) / INITIAL_INVESTMENT * 100):.2f}%")
    print()
    print(f"MINIMUM Portfolio Value: ${min_value:,.2f} on {min_date.strftime('%Y-%m-%d')}")
    print(f"Max Drawdown: {((min_value - INITIAL_INVESTMENT) / INITIAL_INVESTMENT * 100):.2f}%")

    # Save to CSV
    csv_filename = 'research/output/tqqq_portfolio_daily.csv'
    with open(csv_filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Date', 'Portfolio Value'])
        for date, value in zip(dates, portfolio_values):
            writer.writerow([date.strftime('%Y-%m-%d'), f'{value:.2f}'])
    print(f"\nDaily portfolio values saved to '{csv_filename}'")

    return dates, portfolio_values

def plot_portfolio(dates, values):
    """Generate plot of portfolio value over time"""
    plt.figure(figsize=(14, 7))
    plt.plot(dates, values, linewidth=2, color='blue')
    plt.axhline(y=INITIAL_INVESTMENT, color='red', linestyle='--', linewidth=1, label=f'Initial Investment: ${INITIAL_INVESTMENT:,}')

    plt.title(f'TQQQ Portfolio Value Over Time ({START_DATE} to {END_DATE})', fontsize=16, fontweight='bold')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Portfolio Value ($)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=10)

    # Format y-axis as currency
    ax = plt.gca()
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))

    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45, ha='right')

    plt.tight_layout()
    plt.savefig('research/output/tqqq_portfolio.png', dpi=300, bbox_inches='tight')
    print("\nPlot saved as 'research/output/tqqq_portfolio.png'")
    # plt.show()  # Commented out to prevent blocking

def main():
    # Fetch data
    price_data = fetch_tqqq_data()
    if not price_data:
        return

    # Simulate investment
    dates, portfolio_values = simulate_investment(price_data)
    if dates is None:
        return

    # Generate plot
    plot_portfolio(dates, portfolio_values)

if __name__ == "__main__":
    main()
