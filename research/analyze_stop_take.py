import psycopg2
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
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

# Get breakthrough signals
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
  WHERE ush.date > '2025-09-01'
    AND ush.sequence = 1
    AND ush.breakthrough = true
    AND ush.duration_from_date2 > 50
    AND sp.close < (te.max_price * 0.5)
    ORDER BY ush.date;
'''

cur.execute(query)
breakthrough_signals = cur.fetchall()

# Store metrics for each ticker
ticker_metrics_map = {
    signal[0]: {
        'percent_down_from_max': float(signal[4]),
        'duration_from_date1': int(signal[5]) if signal[5] is not None else None,
        'duration_from_date2': int(signal[6]) if signal[6] is not None else None
    }
    for signal in breakthrough_signals
}

print(f"Analyzing {len(breakthrough_signals)} breakthrough signals with -5% stop loss and +20% take profit\n")
print("="*120)

results = []
stop_loss_count = 0
take_profit_count = 0
no_hit_count = 0

for signal in breakthrough_signals:
    ticker, entry_date, entry_price, max_price, percent_down, dur1, dur2 = signal

    # Calculate stop loss and take profit levels
    stop_loss_price = float(entry_price) * 0.95  # -5%
    take_profit_price = float(entry_price) * 1.20  # +20%

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

    metrics = ticker_metrics_map.get(ticker, {})
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
        'percent_down_from_max': metrics.get('percent_down_from_max'),
        'duration_from_date1': metrics.get('duration_from_date1'),
        'duration_from_date2': metrics.get('duration_from_date2')
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
            result['pnl_pct'] = -5.0
            stop_loss_count += 1
            break

        # Check if take profit was hit (using high prices)
        if float(high) >= take_profit_price:
            result['outcome'] = 'TAKE_PROFIT'
            result['exit_date'] = date
            result['exit_price'] = take_profit_price
            result['days_held'] = days_held
            result['pnl_pct'] = 20.0
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
    print(f"{status_icon} {ticker:6s} | Entry: {entry_date} @ ${float(entry_price):6.2f} | {result['outcome']:12s} | Exit: {result['exit_date']} @ {exit_price_str} | Days: {days_str} | P&L: {pnl_str}")

print("="*120)
print(f"\nSUMMARY:")
print(f"Total Signals: {len(results)}")
print(f"Take Profit Hits: {take_profit_count} ({take_profit_count/len(results)*100:.1f}%)")
print(f"Stop Loss Hits: {stop_loss_count} ({stop_loss_count/len(results)*100:.1f}%)")
print(f"No Hit (Still Open): {no_hit_count} ({no_hit_count/len(results)*100:.1f}%)")

# Calculate overall performance
total_pnl = sum([r['pnl_pct'] for r in results if r['pnl_pct'] is not None])
avg_pnl = total_pnl / len(results) if results else 0
avg_days_held = sum([r['days_held'] for r in results if r['days_held'] is not None]) / len(results) if results else 0

print(f"\nPERFORMANCE:")
print(f"Average P&L per trade: {avg_pnl:+.2f}%")
print(f"Total P&L (all trades): {total_pnl:+.2f}%")
print(f"Average days held: {avg_days_held:.1f} days")

# Win rate calculation (excluding NO_HIT)
closed_trades = take_profit_count + stop_loss_count
if closed_trades > 0:
    win_rate = (take_profit_count / closed_trades) * 100
    print(f"Win Rate (closed trades only): {win_rate:.1f}%")

# Calculate what would have happened if we held stop loss positions to the last date
print(f"\n{'='*120}")
print(f"STOP LOSS ANALYSIS - What if we held to the last available date?")
print(f"{'='*120}")

stop_loss_positions = [r for r in results if r['outcome'] == 'STOP_LOSS']
stop_loss_to_last_analysis = []

for position in stop_loss_positions:
    ticker = position['ticker']
    entry_price = position['entry_price']
    entry_date = position['entry_date']

    # Get the last available price for this ticker
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

        stop_loss_to_last_analysis.append({
            'ticker': ticker,
            'entry_price': entry_price,
            'entry_date': entry_date,
            'last_price': last_close,
            'last_date': last_date,
            'pct_change': pct_change
        })

        print(f"{ticker:6s} | Entry: ${entry_price:6.2f} ({entry_date}) | Last: ${last_close:6.2f} ({last_date}) | Change: {pct_change:+7.2f}%")

# Calculate total percentage change
total_stop_loss_pct = sum([p['pct_change'] for p in stop_loss_to_last_analysis])
avg_stop_loss_pct = total_stop_loss_pct / len(stop_loss_to_last_analysis) if stop_loss_to_last_analysis else 0

print(f"\n{'='*120}")
print(f"STOP LOSS POSITIONS - If held to last date:")
print(f"Total positions analyzed: {len(stop_loss_to_last_analysis)}")
print(f"Total percentage change (sum): {total_stop_loss_pct:+.2f}%")
print(f"Average percentage change per position: {avg_stop_loss_pct:+.2f}%")
print(f"{'='*120}")

# Calculate what would have happened if we held take profit positions to the last date
print(f"\n{'='*120}")
print(f"TAKE PROFIT ANALYSIS - What if we held to the last available date?")
print(f"{'='*120}")

take_profit_positions = [r for r in results if r['outcome'] == 'TAKE_PROFIT']
take_profit_to_last_analysis = []

for position in take_profit_positions:
    ticker = position['ticker']
    entry_price = position['entry_price']
    entry_date = position['entry_date']

    # Get the last available price for this ticker
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

        # Calculate the difference from the +20% we took
        difference_from_tp = pct_change - 20.0

        take_profit_to_last_analysis.append({
            'ticker': ticker,
            'entry_price': entry_price,
            'entry_date': entry_date,
            'last_price': last_close,
            'last_date': last_date,
            'pct_change': pct_change,
            'difference_from_tp': difference_from_tp
        })

        outcome_icon = "🟢" if pct_change >= 20.0 else "🔴"
        print(f"{outcome_icon} {ticker:6s} | Entry: ${entry_price:6.2f} ({entry_date}) | Last: ${last_close:6.2f} ({last_date}) | Change: {pct_change:+7.2f}% | vs TP: {difference_from_tp:+7.2f}%")

# Calculate total percentage change
total_tp_pct = sum([p['pct_change'] for p in take_profit_to_last_analysis])
avg_tp_pct = total_tp_pct / len(take_profit_to_last_analysis) if take_profit_to_last_analysis else 0

# Calculate how much we left on the table or saved by exiting at +20%
total_actual_tp = len(take_profit_positions) * 20.0  # We took +20% on each
total_difference = total_tp_pct - total_actual_tp

winners_if_held = len([p for p in take_profit_to_last_analysis if p['pct_change'] >= 20.0])
losers_if_held = len([p for p in take_profit_to_last_analysis if p['pct_change'] < 20.0])

print(f"\n{'='*120}")
print(f"TAKE PROFIT POSITIONS - If held to last date:")
print(f"Total positions analyzed: {len(take_profit_to_last_analysis)}")
print(f"Actual gains taken (16 × 20%): +{total_actual_tp:.2f}%")
print(f"Potential gains if held to last date: {total_tp_pct:+.2f}%")
print(f"Difference (opportunity cost/saved): {total_difference:+.2f}%")
print(f"Average percentage per position if held: {avg_tp_pct:+.2f}%")
print(f"\nPositions still above +20% at last date: {winners_if_held} ({winners_if_held/len(take_profit_to_last_analysis)*100:.1f}%)")
print(f"Positions that fell below +20%: {losers_if_held} ({losers_if_held/len(take_profit_to_last_analysis)*100:.1f}%)")
print(f"{'='*120}")

# Calculate performance of NO_HIT positions
print(f"\n{'='*120}")
print(f"NO HIT ANALYSIS - Positions that never hit stop loss or take profit")
print(f"{'='*120}")

no_hit_positions = [r for r in results if r['outcome'] == 'NO_HIT']
no_hit_analysis = []

for position in no_hit_positions:
    ticker = position['ticker']
    entry_price = position['entry_price']
    entry_date = position['entry_date']
    exit_price = position['exit_price']
    exit_date = position['exit_date']
    pct_change = position['pnl_pct']

    if exit_price is not None and pct_change is not None:
        no_hit_analysis.append({
            'ticker': ticker,
            'entry_price': entry_price,
            'entry_date': entry_date,
            'exit_price': exit_price,
            'exit_date': exit_date,
            'pct_change': pct_change
        })

        outcome_icon = "🟢" if pct_change >= 0 else "🔴"
        print(f"{outcome_icon} {ticker:6s} | Entry: ${entry_price:6.2f} ({entry_date}) | Last: ${exit_price:6.2f} ({exit_date}) | Change: {pct_change:+7.2f}%")

# Calculate total percentage change
total_no_hit_pct = sum([p['pct_change'] for p in no_hit_analysis])
avg_no_hit_pct = total_no_hit_pct / len(no_hit_analysis) if no_hit_analysis else 0

# Count winners and losers
no_hit_winners = len([p for p in no_hit_analysis if p['pct_change'] >= 0])
no_hit_losers = len([p for p in no_hit_analysis if p['pct_change'] < 0])

print(f"\n{'='*120}")
print(f"NO HIT POSITIONS - Summary:")
print(f"Total positions analyzed: {len(no_hit_analysis)}")
print(f"Total percentage change (sum): {total_no_hit_pct:+.2f}%")
print(f"Average percentage change per position: {avg_no_hit_pct:+.2f}%")
print(f"\nPositions with gains: {no_hit_winners} ({no_hit_winners/len(no_hit_analysis)*100:.1f}%)")
print(f"Positions with losses: {no_hit_losers} ({no_hit_losers/len(no_hit_analysis)*100:.1f}%)")
print(f"{'='*120}")

# Final overall summary
print(f"\n{'='*120}")
print(f"OVERALL STRATEGY COMPARISON")
print(f"{'='*120}")
print(f"\nWith Stop Loss (-5%) and Take Profit (+20%) Strategy:")
print(f"  Take Profit positions: 16 × +20% = +320.00%")
print(f"  Stop Loss positions: 50 × -5% = -250.00%")
print(f"  No Hit positions: {total_no_hit_pct:+.2f}%")
print(f"  TOTAL: {320.0 - 250.0 + total_no_hit_pct:+.2f}%")

print(f"\nIf Held All Positions to Last Date (no stops/targets):")
print(f"  Take Profit group would be: {total_tp_pct:+.2f}%")
print(f"  Stop Loss group would be: {total_stop_loss_pct:+.2f}%")
print(f"  No Hit group would be: {total_no_hit_pct:+.2f}%")
print(f"  TOTAL: {total_tp_pct + total_stop_loss_pct + total_no_hit_pct:+.2f}%")

print(f"\nStrategy Performance Difference:")
strategy_total = 320.0 - 250.0 + total_no_hit_pct
hold_all_total = total_tp_pct + total_stop_loss_pct + total_no_hit_pct
difference = strategy_total - hold_all_total
print(f"  With Strategy: {strategy_total:+.2f}%")
print(f"  Hold All: {hold_all_total:+.2f}%")
print(f"  Difference: {difference:+.2f}%")
if difference > 0:
    print(f"  ✓ Strategy outperformed by {difference:.2f}%")
else:
    print(f"  ✗ Hold all would have been better by {abs(difference):.2f}%")
print(f"{'='*120}")

# Analyze percent_down_from_max for Take Profit vs Stop Loss
print(f"\n{'='*120}")
print(f"PERCENT DOWN FROM MAX ANALYSIS - Take Profit vs Stop Loss")
print(f"{'='*120}")

take_profit_pct_down = [r['percent_down_from_max'] for r in results if r['outcome'] == 'TAKE_PROFIT' and r['percent_down_from_max'] is not None]
stop_loss_pct_down = [r['percent_down_from_max'] for r in results if r['outcome'] == 'STOP_LOSS' and r['percent_down_from_max'] is not None]
no_hit_pct_down = [r['percent_down_from_max'] for r in results if r['outcome'] == 'NO_HIT' and r['percent_down_from_max'] is not None]

print(f"\nTAKE PROFIT positions (16 total):")
if take_profit_pct_down:
    avg_tp_pct_down = sum(take_profit_pct_down) / len(take_profit_pct_down)
    min_tp_pct_down = min(take_profit_pct_down)
    max_tp_pct_down = max(take_profit_pct_down)
    print(f"  Average % down from max: {avg_tp_pct_down:.2f}%")
    print(f"  Min % down from max: {min_tp_pct_down:.2f}%")
    print(f"  Max % down from max: {max_tp_pct_down:.2f}%")
    print(f"  Individual values: {sorted(take_profit_pct_down)}")

print(f"\nSTOP LOSS positions (50 total):")
if stop_loss_pct_down:
    avg_sl_pct_down = sum(stop_loss_pct_down) / len(stop_loss_pct_down)
    min_sl_pct_down = min(stop_loss_pct_down)
    max_sl_pct_down = max(stop_loss_pct_down)
    print(f"  Average % down from max: {avg_sl_pct_down:.2f}%")
    print(f"  Min % down from max: {min_sl_pct_down:.2f}%")
    print(f"  Max % down from max: {max_sl_pct_down:.2f}%")
    print(f"  Individual values: {sorted(stop_loss_pct_down)}")

print(f"\nNO HIT positions (11 total):")
if no_hit_pct_down:
    avg_nh_pct_down = sum(no_hit_pct_down) / len(no_hit_pct_down)
    min_nh_pct_down = min(no_hit_pct_down)
    max_nh_pct_down = max(no_hit_pct_down)
    print(f"  Average % down from max: {avg_nh_pct_down:.2f}%")
    print(f"  Min % down from max: {min_nh_pct_down:.2f}%")
    print(f"  Max % down from max: {max_nh_pct_down:.2f}%")
    print(f"  Individual values: {sorted(no_hit_pct_down)}")

print(f"\n{'='*120}")
print(f"KEY DIFFERENCES:")
if take_profit_pct_down and stop_loss_pct_down:
    diff = avg_tp_pct_down - avg_sl_pct_down
    print(f"  Average Take Profit % down from max: {avg_tp_pct_down:.2f}%")
    print(f"  Average Stop Loss % down from max: {avg_sl_pct_down:.2f}%")
    print(f"  Difference: {diff:.2f}%")
    if abs(diff) < 5:
        print(f"  ⚠️  Very similar - percent_down_from_max is NOT a strong predictor")
    elif avg_tp_pct_down < avg_sl_pct_down:
        print(f"  ✓ Take Profit positions were closer to their max (less down)")
        print(f"    → Signals closer to max price may have better momentum")
    else:
        print(f"  ✓ Stop Loss positions were closer to their max (less down)")
        print(f"    → Signals closer to max price may be more prone to failure")

# Show detailed breakdown by ticker for better insight
print(f"\n{'='*120}")
print(f"TAKE PROFIT POSITIONS - Detailed Breakdown:")
print(f"{'='*120}")
tp_positions = [(r['ticker'], r['percent_down_from_max'], r['pnl_pct']) for r in results if r['outcome'] == 'TAKE_PROFIT' and r['percent_down_from_max'] is not None]
tp_positions.sort(key=lambda x: x[1])  # Sort by percent_down_from_max
for ticker, pct_down, pnl in tp_positions:
    print(f"  {ticker:6s}: {pct_down:5.2f}% down from max → Hit +20% TP")

print(f"\n{'='*120}")
print(f"STOP LOSS POSITIONS - Detailed Breakdown:")
print(f"{'='*120}")
sl_positions = [(r['ticker'], r['percent_down_from_max'], r['pnl_pct']) for r in results if r['outcome'] == 'STOP_LOSS' and r['percent_down_from_max'] is not None]
sl_positions.sort(key=lambda x: x[1])  # Sort by percent_down_from_max
for ticker, pct_down, pnl in sl_positions:
    print(f"  {ticker:6s}: {pct_down:5.2f}% down from max → Hit -5% SL")

print(f"{'='*120}")

# Analyze duration_from_date1 and duration_from_date2 for Take Profit vs Stop Loss
print(f"\n{'='*120}")
print(f"DURATION ANALYSIS - Take Profit vs Stop Loss")
print(f"{'='*120}")

# Extract duration values for each group
tp_dur1 = [r['duration_from_date1'] for r in results if r['outcome'] == 'TAKE_PROFIT' and r['duration_from_date1'] is not None]
tp_dur2 = [r['duration_from_date2'] for r in results if r['outcome'] == 'TAKE_PROFIT' and r['duration_from_date2'] is not None]

sl_dur1 = [r['duration_from_date1'] for r in results if r['outcome'] == 'STOP_LOSS' and r['duration_from_date1'] is not None]
sl_dur2 = [r['duration_from_date2'] for r in results if r['outcome'] == 'STOP_LOSS' and r['duration_from_date2'] is not None]

nh_dur1 = [r['duration_from_date1'] for r in results if r['outcome'] == 'NO_HIT' and r['duration_from_date1'] is not None]
nh_dur2 = [r['duration_from_date2'] for r in results if r['outcome'] == 'NO_HIT' and r['duration_from_date2'] is not None]

print(f"\nDURATION_FROM_DATE1 Analysis:")
print(f"{'='*120}")

if tp_dur1:
    avg_tp_dur1 = sum(tp_dur1) / len(tp_dur1)
    min_tp_dur1 = min(tp_dur1)
    max_tp_dur1 = max(tp_dur1)
    print(f"\nTAKE PROFIT positions ({len(tp_dur1)} total):")
    print(f"  Average duration_from_date1: {avg_tp_dur1:.1f} days")
    print(f"  Min: {min_tp_dur1} days, Max: {max_tp_dur1} days")
    print(f"  Values: {sorted(tp_dur1)}")

if sl_dur1:
    avg_sl_dur1 = sum(sl_dur1) / len(sl_dur1)
    min_sl_dur1 = min(sl_dur1)
    max_sl_dur1 = max(sl_dur1)
    print(f"\nSTOP LOSS positions ({len(sl_dur1)} total):")
    print(f"  Average duration_from_date1: {avg_sl_dur1:.1f} days")
    print(f"  Min: {min_sl_dur1} days, Max: {max_sl_dur1} days")
    print(f"  Values: {sorted(sl_dur1)}")

if nh_dur1:
    avg_nh_dur1 = sum(nh_dur1) / len(nh_dur1)
    min_nh_dur1 = min(nh_dur1)
    max_nh_dur1 = max(nh_dur1)
    print(f"\nNO HIT positions ({len(nh_dur1)} total):")
    print(f"  Average duration_from_date1: {avg_nh_dur1:.1f} days")
    print(f"  Min: {min_nh_dur1} days, Max: {max_nh_dur1} days")
    print(f"  Values: {sorted(nh_dur1)}")

if tp_dur1 and sl_dur1:
    diff_dur1 = avg_tp_dur1 - avg_sl_dur1
    print(f"\nKEY DIFFERENCE (duration_from_date1):")
    print(f"  Take Profit avg: {avg_tp_dur1:.1f} days")
    print(f"  Stop Loss avg: {avg_sl_dur1:.1f} days")
    print(f"  Difference: {diff_dur1:+.1f} days")
    if abs(diff_dur1) > 20:
        if diff_dur1 > 0:
            print(f"  ✓ Take Profit positions had LONGER duration_from_date1")
            print(f"    → Older trendlines may indicate stronger support/resistance")
        else:
            print(f"  ✓ Stop Loss positions had LONGER duration_from_date1")
            print(f"    → Older trendlines may be less relevant")
    else:
        print(f"  ⚠️  Similar durations - duration_from_date1 is NOT a strong predictor")

print(f"\n{'='*120}")
print(f"DURATION_FROM_DATE2 Analysis:")
print(f"{'='*120}")

if tp_dur2:
    avg_tp_dur2 = sum(tp_dur2) / len(tp_dur2)
    min_tp_dur2 = min(tp_dur2)
    max_tp_dur2 = max(tp_dur2)
    print(f"\nTAKE PROFIT positions ({len(tp_dur2)} total):")
    print(f"  Average duration_from_date2: {avg_tp_dur2:.1f} days")
    print(f"  Min: {min_tp_dur2} days, Max: {max_tp_dur2} days")
    print(f"  Values: {sorted(tp_dur2)}")

if sl_dur2:
    avg_sl_dur2 = sum(sl_dur2) / len(sl_dur2)
    min_sl_dur2 = min(sl_dur2)
    max_sl_dur2 = max(sl_dur2)
    print(f"\nSTOP LOSS positions ({len(sl_dur2)} total):")
    print(f"  Average duration_from_date2: {avg_sl_dur2:.1f} days")
    print(f"  Min: {min_sl_dur2} days, Max: {max_sl_dur2} days")
    print(f"  Values: {sorted(sl_dur2)}")

if nh_dur2:
    avg_nh_dur2 = sum(nh_dur2) / len(nh_dur2)
    min_nh_dur2 = min(nh_dur2)
    max_nh_dur2 = max(nh_dur2)
    print(f"\nNO HIT positions ({len(nh_dur2)} total):")
    print(f"  Average duration_from_date2: {avg_nh_dur2:.1f} days")
    print(f"  Min: {min_nh_dur2} days, Max: {max_nh_dur2} days")
    print(f"  Values: {sorted(nh_dur2)}")

if tp_dur2 and sl_dur2:
    diff_dur2 = avg_tp_dur2 - avg_sl_dur2
    print(f"\nKEY DIFFERENCE (duration_from_date2):")
    print(f"  Take Profit avg: {avg_tp_dur2:.1f} days")
    print(f"  Stop Loss avg: {avg_sl_dur2:.1f} days")
    print(f"  Difference: {diff_dur2:+.1f} days")
    if abs(diff_dur2) > 50:
        if diff_dur2 > 0:
            print(f"  ✓ Take Profit positions had LONGER duration_from_date2")
            print(f"    → More mature trendlines may have stronger validity")
        else:
            print(f"  ✓ Stop Loss positions had LONGER duration_from_date2")
            print(f"    → Very old trendlines may have lost relevance")
    else:
        print(f"  ⚠️  Similar durations - duration_from_date2 is NOT a strong predictor")

# Detailed breakdown
print(f"\n{'='*120}")
print(f"TAKE PROFIT - Detailed Duration Breakdown:")
print(f"{'='*120}")
tp_positions_dur = [(r['ticker'], r['duration_from_date1'], r['duration_from_date2'])
                    for r in results if r['outcome'] == 'TAKE_PROFIT' and r['duration_from_date2'] is not None]
tp_positions_dur.sort(key=lambda x: x[2])  # Sort by duration_from_date2
for ticker, dur1, dur2 in tp_positions_dur:
    print(f"  {ticker:6s}: dur1={dur1:4d} days, dur2={dur2:4d} days → Hit +20% TP")

print(f"\n{'='*120}")
print(f"STOP LOSS - Detailed Duration Breakdown:")
print(f"{'='*120}")
sl_positions_dur = [(r['ticker'], r['duration_from_date1'], r['duration_from_date2'])
                    for r in results if r['outcome'] == 'STOP_LOSS' and r['duration_from_date2'] is not None]
sl_positions_dur.sort(key=lambda x: x[2])  # Sort by duration_from_date2
for ticker, dur1, dur2 in sl_positions_dur:
    print(f"  {ticker:6s}: dur1={dur1:4d} days, dur2={dur2:4d} days → Hit -5% SL")

print(f"{'='*120}")

cur.close()
conn.close()
