import psycopg2
from dotenv import load_dotenv
import os
from decimal import Decimal

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    database=os.getenv('DB_NAME'),
    user=os.getenv('DB_USERNAME'),
    password=os.getenv('DB_PASSWORD')
)

cur = conn.cursor()

# Get breakthrough signals for July-August 2025 with duration_from_date2 > 150
query = '''
SELECT ush.ticker,
         ush.date,
         sp.close as current_price,
         te.max_price,
         ROUND(((te.max_price - sp.close) / te.max_price * 100)::numeric, 2) as percent_down_from_max,
         ush.duration_from_date1,
         ush.duration_from_date2
  FROM upper_status_historical ush
  JOIN stock_prices sp ON ush.ticker = sp.ticker AND ush.date = sp.date
  JOIN ticker_extremes te ON ush.ticker = te.ticker
  WHERE ush.date > '2025-07-01' and ush.date < '2025-09-01'
    AND ush.sequence = 1
    AND ush.breakthrough = true
    AND ush.duration_from_date2 > 150
    AND sp.close < (te.max_price * 0.5)
    ORDER BY ush.date;
'''

cur.execute(query)
breakthrough_signals = cur.fetchall()

print(f"Analyzing {len(breakthrough_signals)} breakthrough signals (July-August 2025)")
print(f"Filter: duration_from_date2 > 150 days")
print(f"Strategy: -10% stop loss and +30% take profit\n")
print("="*120)

results = []
stop_loss_count = 0
take_profit_count = 0
no_hit_count = 0

for signal in breakthrough_signals:
    ticker, entry_date, entry_price, max_price, percent_down, dur1, dur2 = signal

    # Calculate stop loss and take profit levels
    stop_loss_price = float(entry_price) * 0.90  # -10%
    take_profit_price = float(entry_price) * 1.30  # +30%

    # Get subsequent price data for this ticker
    price_query = '''
    SELECT date, high, low, close
    FROM stock_prices
    WHERE ticker = %s
      AND date > %s
    ORDER BY date ASC
    LIMIT 100;
    '''

    cur.execute(price_query, (ticker, entry_date))
    future_prices = cur.fetchall()

    result = {
        'ticker': ticker,
        'entry_date': entry_date,
        'entry_price': float(entry_price),
        'stop_loss': stop_loss_price,
        'take_profit': take_profit_price,
        'outcome': 'NO_HIT',
        'exit_date': None,
        'exit_price': None,
        'days_held': None,
        'pnl_pct': None,
        'percent_down_from_max': float(percent_down),
        'duration_from_date2': int(dur2)
    }

    # Check each day to see which level was hit first
    for i, (date, high, low, close) in enumerate(future_prices):
        days_held = i + 1

        # Check if stop loss was hit (using low prices)
        if float(low) <= stop_loss_price:
            result['outcome'] = 'STOP_LOSS'
            result['exit_date'] = date
            result['exit_price'] = stop_loss_price
            result['days_held'] = days_held
            result['pnl_pct'] = -10.0
            stop_loss_count += 1
            break

        # Check if take profit was hit (using high prices)
        if float(high) >= take_profit_price:
            result['outcome'] = 'TAKE_PROFIT'
            result['exit_date'] = date
            result['exit_price'] = take_profit_price
            result['days_held'] = days_held
            result['pnl_pct'] = 30.0
            take_profit_count += 1
            break

    if result['outcome'] == 'NO_HIT':
        no_hit_count += 1
        # Get last available price if no exit
        if future_prices:
            last_date, _, _, last_close = future_prices[-1]
            result['exit_date'] = last_date
            result['exit_price'] = float(last_close)
            result['days_held'] = len(future_prices)
            result['pnl_pct'] = round(((float(last_close) - float(entry_price)) / float(entry_price) * 100), 2)

    results.append(result)

    # Print result
    status_icon = "🟢" if result['outcome'] == 'TAKE_PROFIT' else "🔴" if result['outcome'] == 'STOP_LOSS' else "⚪"
    exit_price_str = f"${result['exit_price']:6.2f}" if result['exit_price'] is not None else "N/A"
    days_str = f"{result['days_held']:3d}" if result['days_held'] is not None else "N/A"
    pnl_str = f"{result['pnl_pct']:+6.2f}%" if result['pnl_pct'] is not None else "N/A"
    print(f"{status_icon} {ticker:6s} | Entry: {entry_date} @ ${float(entry_price):6.2f} | {result['outcome']:12s} | Exit: {result['exit_date']} @ {exit_price_str} | Days: {days_str} | P&L: {pnl_str} | Dur2: {dur2:4d}")

print("="*120)
print(f"\nSUMMARY:")
print(f"Total Signals: {len(results)}")
print(f"Take Profit Hits: {take_profit_count} ({take_profit_count/len(results)*100:.1f}%)")
print(f"Stop Loss Hits: {stop_loss_count} ({stop_loss_count/len(results)*100:.1f}%)")
print(f"No Hit (Still Open): {no_hit_count} ({no_hit_count/len(results)*100:.1f}%)")

# Calculate overall performance with strategy
total_pnl = sum([r['pnl_pct'] for r in results if r['pnl_pct'] is not None])
avg_pnl = total_pnl / len(results) if results else 0
avg_days_held = sum([r['days_held'] for r in results if r['days_held'] is not None]) / len(results) if results else 0

print(f"\nPERFORMANCE WITH STRATEGY:")
print(f"Average P&L per trade: {avg_pnl:+.2f}%")
print(f"Total P&L (all trades): {total_pnl:+.2f}%")
print(f"Average days held: {avg_days_held:.1f} days")

# Win rate calculation (excluding NO_HIT)
closed_trades = take_profit_count + stop_loss_count
if closed_trades > 0:
    win_rate = (take_profit_count / closed_trades) * 100
    print(f"Win Rate (closed trades only): {win_rate:.1f}%")

# Now calculate what would have happened if held to last date
print(f"\n{'='*120}")
print(f"ANALYSIS - If held to last available date")
print(f"{'='*120}")

# For Take Profit positions
tp_to_last = []
for result in results:
    if result['outcome'] == 'TAKE_PROFIT':
        ticker = result['ticker']
        entry_price = result['entry_price']

        last_price_query = '''
        SELECT date, close
        FROM stock_prices
        WHERE ticker = %s
        ORDER BY date DESC
        LIMIT 1;
        '''

        cur.execute(last_price_query, (ticker,))
        last_result = cur.fetchone()

        if last_result:
            last_date, last_close = last_result
            last_close = float(last_close)
            pct_change = ((last_close - entry_price) / entry_price * 100)
            tp_to_last.append(pct_change)
            print(f"🟢 TP  {ticker:6s}: Entry ${entry_price:6.2f} → Last ${last_close:6.2f} ({last_date}) = {pct_change:+7.2f}% (took +30%)")

# For Stop Loss positions
sl_to_last = []
for result in results:
    if result['outcome'] == 'STOP_LOSS':
        ticker = result['ticker']
        entry_price = result['entry_price']

        last_price_query = '''
        SELECT date, close
        FROM stock_prices
        WHERE ticker = %s
        ORDER BY date DESC
        LIMIT 1;
        '''

        cur.execute(last_price_query, (ticker,))
        last_result = cur.fetchone()

        if last_result:
            last_date, last_close = last_result
            last_close = float(last_close)
            pct_change = ((last_close - entry_price) / entry_price * 100)
            sl_to_last.append(pct_change)
            print(f"🔴 SL  {ticker:6s}: Entry ${entry_price:6.2f} → Last ${last_close:6.2f} ({last_date}) = {pct_change:+7.2f}% (took -10%)")

# For No Hit positions (already have the data)
nh_to_last = [r['pnl_pct'] for r in results if r['outcome'] == 'NO_HIT' and r['pnl_pct'] is not None]

print(f"\n{'='*120}")
print(f"COMPARISON: Strategy vs Hold All")
print(f"{'='*120}")

# With Strategy
tp_strategy_total = take_profit_count * 30.0
sl_strategy_total = stop_loss_count * -10.0
nh_strategy_total = sum(nh_to_last)
strategy_total = tp_strategy_total + sl_strategy_total + nh_strategy_total

print(f"\nWITH STRATEGY (-10% SL / +30% TP):")
print(f"  Take Profit group: {take_profit_count} × +30% = {tp_strategy_total:+.2f}%")
print(f"  Stop Loss group: {stop_loss_count} × -10% = {sl_strategy_total:+.2f}%")
print(f"  No Hit group: {sum(nh_to_last):+.2f}%")
print(f"  TOTAL: {strategy_total:+.2f}%")

# If Held All
tp_hold_total = sum(tp_to_last)
sl_hold_total = sum(sl_to_last)
nh_hold_total = sum(nh_to_last)
hold_total = tp_hold_total + sl_hold_total + nh_hold_total

print(f"\nIF HELD ALL TO LAST DATE:")
print(f"  Take Profit group: {tp_hold_total:+.2f}%")
print(f"  Stop Loss group: {sl_hold_total:+.2f}%")
print(f"  No Hit group: {nh_hold_total:+.2f}%")
print(f"  TOTAL: {hold_total:+.2f}%")

difference = strategy_total - hold_total
print(f"\nDIFFERENCE:")
print(f"  Strategy: {strategy_total:+.2f}%")
print(f"  Hold All: {hold_total:+.2f}%")
print(f"  Strategy vs Hold: {difference:+.2f}%")

if difference > 0:
    print(f"  ✓ Strategy OUTPERFORMED by {difference:.2f}%")
else:
    print(f"  ✗ Hold all would have been better by {abs(difference):.2f}%")

print(f"{'='*120}")

cur.close()
conn.close()
