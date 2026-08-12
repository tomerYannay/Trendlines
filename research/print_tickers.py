#!/usr/bin/env python3

import pandas as pd

# Read the CSV file
df = pd.read_csv('research/output/results.csv')

# Extract unique tickers and sort them
tickers = sorted(df['ticker'].unique())

# Print tickers with comma separator
print(', '.join(tickers))